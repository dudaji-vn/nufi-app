"""tests/test_cmp340_scan_diff_guard_ci.py -- scan --diff + guard --ci 테스트 (v0.7.5 / CMP-340).

시나리오:
1. scan --diff: staged 변경 PII 스캔 (변경 행만)
2. scan --diff <ref>: ref 대비 스캔
3. guard --ci: 출력 형식 검증 (GitHub Actions annotation)
4. guard --ci: exit code 검증
"""
from __future__ import annotations

import io
import json
import os
import subprocess
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

import pytest

from enforcement.scan_cmd import scan_diff, _git_diff_changed_lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_git_repo(tmp_path: Path) -> Path:
    """Initialise a temporary git repo with an initial commit."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    readme = tmp_path / "README.md"
    readme.write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    return tmp_path


# ===========================================================================
# scan --diff tests
# ===========================================================================

class TestScanDiffStaged:
    """scan --diff (default HEAD): staged 변경 행만 PII 스캔."""

    def test_pii_in_staged_changes(self, tmp_path: Path):
        """Staged 파일에 PII 추가 → 변경 행에서 PII 발견."""
        repo = _init_git_repo(tmp_path)
        pii_file = repo / "data.txt"
        pii_file.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "data.txt"], cwd=str(repo), capture_output=True, check=True)

        result = scan_diff(ref="HEAD", repo=str(repo))
        assert result.files_scanned >= 1
        assert result.has_pii
        assert len(result.findings) >= 1
        pii_files = {f.file for f in result.findings}
        assert any("data.txt" in fp for fp in pii_files)

    def test_clean_staged_no_findings(self, tmp_path: Path):
        """Staged 파일에 PII 없음 → 발견 없음."""
        repo = _init_git_repo(tmp_path)
        clean_file = repo / "notes.txt"
        clean_file.write_text("Just normal text, no PII here.\n", encoding="utf-8")
        subprocess.run(["git", "add", "notes.txt"], cwd=str(repo), capture_output=True, check=True)

        result = scan_diff(ref="HEAD", repo=str(repo))
        assert result.files_scanned >= 1
        assert not result.has_pii
        assert len(result.findings) == 0

    def test_only_changed_lines_scanned(self, tmp_path: Path):
        """기존 PII 행은 무시, 새로 추가된 행만 스캔."""
        repo = _init_git_repo(tmp_path)
        # Create a file with PII and commit it
        data = repo / "existing.txt"
        data.write_text("old email: old@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add existing"], cwd=str(repo), capture_output=True, check=True)

        # Now add a new line with PII
        data.write_text("old email: old@example.com\nnew email: new@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "existing.txt"], cwd=str(repo), capture_output=True, check=True)

        result = scan_diff(ref="HEAD", repo=str(repo))
        # Should only find PII in the new line (line 2), not old line (line 1)
        if result.findings:
            for f in result.findings:
                if "existing.txt" in f.file:
                    assert f.line == 2, "Should only scan the newly added line"


class TestScanDiffRef:
    """scan --diff <ref>: 특정 ref 대비 변경분 스캔."""

    def test_diff_against_ref(self, tmp_path: Path):
        """특정 커밋 대비 변경 스캔."""
        repo = _init_git_repo(tmp_path)
        # Add PII file in a new commit (use email, reliably detected)
        pii_file = repo / "secret.txt"
        pii_file.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add pii"], cwd=str(repo), capture_output=True, check=True)

        result = scan_diff(ref="HEAD~1", repo=str(repo))
        assert result.files_scanned >= 1
        assert result.has_pii

    def test_diff_no_changes(self, tmp_path: Path):
        """변경 없으면 빈 결과."""
        repo = _init_git_repo(tmp_path)
        result = scan_diff(ref="HEAD", repo=str(repo))
        assert result.files_scanned == 0
        assert len(result.findings) == 0


class TestScanDiffFormat:
    """scan --diff with --format text|json|sarif 지원."""

    def test_diff_json_output(self, tmp_path: Path, capsys):
        """scan --diff --format json 출력 검증."""
        from enforcement.scan_cmd import cmd_scan
        repo = _init_git_repo(tmp_path)
        pii_file = repo / "data.txt"
        pii_file.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "data.txt"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            target=None, diff="HEAD", format="json", json=False,
            check_injection=False, fail_on_pii=False,
            profile=None, recursive=False, watch=False,
            git_staged=False, clear_cache=False,
        )
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_scan(args)
        finally:
            os.chdir(old_cwd)

        assert ret == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "findings" in data
        assert "scan_target" in data


# ===========================================================================
# _git_diff_changed_lines tests
# ===========================================================================

class TestGitDiffChangedLines:
    """_git_diff_changed_lines 파싱 검증."""

    def test_parse_staged_diff(self, tmp_path: Path):
        """Staged 변경의 행 번호 파싱."""
        repo = _init_git_repo(tmp_path)
        f = repo / "test.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        subprocess.run(["git", "add", "test.txt"], cwd=str(repo), capture_output=True, check=True)

        result = _git_diff_changed_lines("HEAD", repo=str(repo))
        assert "test.txt" in result
        assert 1 in result["test.txt"]
        assert 2 in result["test.txt"]
        assert 3 in result["test.txt"]

    def test_empty_when_no_changes(self, tmp_path: Path):
        """변경 없으면 빈 dict."""
        repo = _init_git_repo(tmp_path)
        result = _git_diff_changed_lines("HEAD", repo=str(repo))
        assert result == {}


# ===========================================================================
# guard --ci tests
# ===========================================================================

class TestGuardCiClean:
    """guard --ci: PII 없으면 OK + exit 0."""

    def test_ci_clean_exit_0(self, tmp_path: Path, capsys):
        """변경분에 PII 없으면 exit 0 + OK 메시지."""
        from enforcement.guard_cmd import cmd_guard
        repo = _init_git_repo(tmp_path)
        clean = repo / "notes.txt"
        clean.write_text("Just normal text.\n", encoding="utf-8")
        subprocess.run(["git", "add", "notes.txt"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            target=None, policy_action_guard="warn", format="text",
            output=None, strict=False,
            ci=True, diff_ref="HEAD", check_injection=False,
        )
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_guard(args)
        finally:
            os.chdir(old_cwd)

        assert ret == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out


class TestGuardCiPiiDetected:
    """guard --ci: PII 있으면 annotation + exit 1."""

    def test_ci_pii_exit_1(self, tmp_path: Path, capsys):
        """변경분에 PII 있으면 exit 1 + GitHub Actions annotation."""
        from enforcement.guard_cmd import cmd_guard
        repo = _init_git_repo(tmp_path)
        pii = repo / "secret.txt"
        pii.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "secret.txt"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            target=None, policy_action_guard="warn", format="text",
            output=None, strict=False,
            ci=True, diff_ref="HEAD", check_injection=False,
        )
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_guard(args)
        finally:
            os.chdir(old_cwd)

        assert ret == 1
        captured = capsys.readouterr()
        # GitHub Actions annotation format
        assert "::error file=" in captured.out
        assert "PII detected:" in captured.out

    def test_ci_annotation_format(self, tmp_path: Path, capsys):
        """GitHub Actions annotation 형식: ::error file=path,line=N::PII detected: TYPE."""
        from enforcement.guard_cmd import cmd_guard
        repo = _init_git_repo(tmp_path)
        pii = repo / "data.txt"
        pii.write_text("이메일: user@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "data.txt"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            target=None, policy_action_guard="warn", format="text",
            output=None, strict=False,
            ci=True, diff_ref="HEAD", check_injection=False,
        )
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_guard(args)
        finally:
            os.chdir(old_cwd)

        captured = capsys.readouterr()
        # Each annotation line should match the expected format
        annotation_lines = [
            l for l in captured.out.splitlines() if l.startswith("::error")
        ]
        assert len(annotation_lines) >= 1
        for line in annotation_lines:
            assert line.startswith("::error file=")
            assert ",line=" in line
            assert "::PII detected:" in line


class TestGuardCiDiffRef:
    """guard --ci --diff-ref: 특정 ref 대비 CI 스캔."""

    def test_ci_with_diff_ref(self, tmp_path: Path, capsys):
        """--diff-ref HEAD~1 로 직전 커밋 대비 스캔."""
        from enforcement.guard_cmd import cmd_guard
        repo = _init_git_repo(tmp_path)
        pii = repo / "secret.txt"
        pii.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add pii"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            target=None, policy_action_guard="warn", format="text",
            output=None, strict=False,
            ci=True, diff_ref="HEAD~1", check_injection=False,
        )
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_guard(args)
        finally:
            os.chdir(old_cwd)

        assert ret == 1
        captured = capsys.readouterr()
        assert "::error file=" in captured.out


class TestGuardCiNoChanges:
    """guard --ci: 변경 없으면 OK + exit 0."""

    def test_ci_no_changes_exit_0(self, tmp_path: Path, capsys):
        from enforcement.guard_cmd import cmd_guard
        repo = _init_git_repo(tmp_path)

        args = SimpleNamespace(
            target=None, policy_action_guard="warn", format="text",
            output=None, strict=False,
            ci=True, diff_ref="HEAD", check_injection=False,
        )
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_guard(args)
        finally:
            os.chdir(old_cwd)

        assert ret == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
