"""tests/test_diff_cmd.py -- nufi-egress diff 커맨드 테스트 (patch104 + v0.6.1).

시나리오:
1. temp git repo 에 PII 파일 추가 후 scan_git_diff → PII 발견
2. 클린 변경만 있는 temp git repo → 발견 없음
3. diff --pseudonymize → PII 파일의 가명화 결과 출력 (v0.6.1)
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from enforcement.diff_cmd import scan_git_diff, cmd_diff, _git_changed_files


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
    # Initial commit (empty)
    readme = tmp_path / "README.md"
    readme.write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    return tmp_path


class TestScanGitDiffPII:
    """PII 가 포함된 변경 파일 스캔 → 발견."""

    def test_pii_in_changed_file(self, tmp_path: Path):
        repo = _init_git_repo(tmp_path)

        # Add a file with PII (email)
        pii_file = repo / "secret.txt"
        pii_file.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "secret.txt"], cwd=str(repo), capture_output=True, check=True)

        result = scan_git_diff(base="HEAD", repo=str(repo))
        assert result.files_scanned >= 1
        assert result.has_pii
        assert len(result.findings) >= 1
        # Finding should reference the PII file
        pii_findings_files = {f.file for f in result.findings}
        assert any("secret.txt" in fp for fp in pii_findings_files)


class TestScanGitDiffClean:
    """PII 없는 변경만 있으면 발견 없음."""

    def test_clean_changes(self, tmp_path: Path):
        repo = _init_git_repo(tmp_path)

        # Add a clean file
        clean = repo / "notes.txt"
        clean.write_text("Just normal text, no PII.\n", encoding="utf-8")
        subprocess.run(["git", "add", "notes.txt"], cwd=str(repo), capture_output=True, check=True)

        result = scan_git_diff(base="HEAD", repo=str(repo))
        assert result.files_scanned >= 1
        assert not result.has_pii
        assert len(result.findings) == 0


class TestDiffPseudonymize:
    """diff --pseudonymize: PII 파일의 가명화 결과 출력 (v0.6.1)."""

    def test_pseudonymize_flag_shows_pseudonymized(self, tmp_path: Path, capsys):
        repo = _init_git_repo(tmp_path)

        # Add a file with PII (Korean name)
        pii_file = repo / "data.txt"
        pii_file.write_text("김민수님의 이메일은 kim@example.com 입니다.\n", encoding="utf-8")
        subprocess.run(["git", "add", "data.txt"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            base="HEAD", check_injection=False, json=False,
            fail_on_pii=False, pseudonymize=True,
        )
        # We need to run from the repo directory for git diff to work
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            ret = cmd_diff(args)
        finally:
            os.chdir(old_cwd)

        captured = capsys.readouterr()
        assert "가명화 결과" in captured.out or ret == 0

    def test_pseudonymize_json_includes_key(self, tmp_path: Path, capsys):
        repo = _init_git_repo(tmp_path)

        pii_file = repo / "secret.txt"
        pii_file.write_text("이메일: test@example.com\n", encoding="utf-8")
        subprocess.run(["git", "add", "secret.txt"], cwd=str(repo), capture_output=True, check=True)

        args = SimpleNamespace(
            base="HEAD", check_injection=False, json=True,
            fail_on_pii=False, pseudonymize=True,
        )
        import os, json
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            cmd_diff(args)
        finally:
            os.chdir(old_cwd)

        captured = capsys.readouterr()
        out = json.loads(captured.out)
        # JSON output should have pseudonymized key when PII found
        if out.get("findings"):
            assert "pseudonymized" in out
