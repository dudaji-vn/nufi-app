"""tests/test_scan_cmd.py — nufi-egress scan 커맨드 테스트 (patch86, patch88, patch91, patch97, patch137, v0.7.0).

시나리오:
1. 단일 파일 스캔 → PII 발견
2. 디렉터리 재귀 스캔 → 여러 파일에서 PII 발견
3. --fail-on-pii → exit code 1
4. 클린 디렉터리 → exit code 0
5. .nufiignore 패턴 준수
6. --exclude 플래그 동작
7. .nufiignore 없을 때 기본 동작
8. --dry-run 모드: 파일 미수정
9. --redact 모드: 파일 수정 + 백업 생성
10. --redact --no-backup: 백업 없이 수정
11. --stats 플래그: 요약 통계 출력
12. --parallel N: 멀티스레드 스캔 결과가 순차 스캔과 동일
13. --verbose 플래그: 발견 항목별 상세 출력
14. .nufi_ignore_findings.yaml 오탐 억제 (patch178)
15. --format csv: CSV 출력 (patch180)
16. --baseline PATH: 이전 결과 대비 신규 발견만 출력 (patch181)
17. --count-only: 발견 건수만 출력 (patch182)
18. --min-score FLOAT: 최소 신뢰도 이하 필터링 (patch186)
19. --only-types LIST: 특정 엔티티 타입만 출력 (patch188)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from enforcement.scan_cmd import (
    scan_path, load_nufiignore, scan_result_to_sarif, redact_path,
    load_suppressions, apply_suppressions, ScanFinding, ScanResult,
    scan_recursive, RecursiveScanResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pii_file(tmp_path: Path) -> Path:
    """PII 가 포함된 단일 파일."""
    f = tmp_path / "data.txt"
    f.write_text("홍길동 주민번호 900101-1234567\n정상 라인\n", encoding="utf-8")
    return f


@pytest.fixture()
def pii_dir(tmp_path: Path) -> Path:
    """여러 파일에 PII 가 분산된 디렉터리."""
    (tmp_path / "a.txt").write_text("이메일: test@example.com\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.md").write_text("전화번호 010-1234-5678 입니다\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def clean_dir(tmp_path: Path) -> Path:
    """PII 없는 클린 디렉터리."""
    (tmp_path / "readme.txt").write_text("Hello world\nNo PII here.\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("Just some notes.\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_file_scan_finds_pii(pii_file: Path):
    """단일 파일 스캔에서 PII 를 탐지한다."""
    result = scan_path(pii_file)
    assert result.files_scanned == 1
    assert result.has_pii
    assert len(result.findings) >= 1
    # 주민번호 탐지 확인
    types = {f.finding_type for f in result.findings}
    assert any("PII:" in t for t in types)


def test_directory_scan_finds_pii_across_files(pii_dir: Path):
    """디렉터리 재귀 스캔에서 여러 파일의 PII 를 탐지한다."""
    result = scan_path(pii_dir)
    assert result.files_scanned >= 2
    assert result.files_with_findings >= 2
    assert result.has_pii
    # 여러 파일에서 발견
    files_with = {f.file for f in result.findings}
    assert len(files_with) >= 2


def test_fail_on_pii_returns_exit_code_1(pii_file: Path):
    """--fail-on-pii 플래그: PII 발견 시 exit code 1."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=True,
        fail_on_pii=True,
        exclude=None,
    )
    rc = cmd_scan(args)
    assert rc == 1


def test_clean_directory_returns_exit_code_0(clean_dir: Path):
    """클린 디렉터리: exit code 0."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(clean_dir),
        pattern=None,
        check_injection=False,
        json=True,
        fail_on_pii=True,
        exclude=None,
    )
    rc = cmd_scan(args)
    assert rc == 0


# ---------------------------------------------------------------------------
# .nufiignore / --exclude tests (patch85)
# ---------------------------------------------------------------------------

def test_nufiignore_patterns_respected(tmp_path: Path):
    """.nufiignore 에 명시된 패턴과 매칭되는 파일은 스캔에서 제외된다."""
    # Create a .nufiignore in the scan root
    (tmp_path / ".nufiignore").write_text(
        "# comments are ignored\n"
        "secret/**\n"
        "*.log\n",
        encoding="utf-8",
    )
    # Create files that should be excluded
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "pii.txt").write_text(
        "주민번호 900101-1234567\n", encoding="utf-8"
    )
    (tmp_path / "app.log").write_text(
        "이메일: test@example.com\n", encoding="utf-8"
    )
    # Create a file that should be scanned
    (tmp_path / "main.txt").write_text("Hello world\n", encoding="utf-8")

    # exclude=None triggers .nufiignore loading
    result = scan_path(tmp_path, exclude=None)
    # main.txt + .nufiignore scanned (secret/pii.txt and app.log excluded)
    assert result.files_scanned == 2  # main.txt + .nufiignore itself
    assert not result.has_pii


def test_exclude_flag_works(tmp_path: Path):
    """--exclude 플래그로 전달된 패턴이 스캔에서 제외된다."""
    # No .nufiignore — use explicit exclude list
    sub = tmp_path / "logs"
    sub.mkdir()
    (sub / "audit.txt").write_text(
        "주민번호 900101-1234567\n", encoding="utf-8"
    )
    (tmp_path / "data.txt").write_text(
        "이메일: test@example.com\n", encoding="utf-8"
    )

    # Exclude logs/** via explicit parameter
    result = scan_path(tmp_path, exclude=["logs/**"])
    # Only data.txt scanned
    assert result.files_scanned == 1
    scanned_files = {f.file for f in result.findings}
    assert all("logs" not in f for f in scanned_files)


def test_default_scan_without_nufiignore(tmp_path: Path):
    """.nufiignore 가 없으면 모든 파일이 스캔된다."""
    # No .nufiignore in tmp_path
    (tmp_path / "a.txt").write_text(
        "주민번호 900101-1234567\n", encoding="utf-8"
    )
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text(
        "이메일: test@example.com\n", encoding="utf-8"
    )

    # exclude=None but no .nufiignore → scan all
    result = scan_path(tmp_path, exclude=None)
    assert result.files_scanned == 2
    assert result.has_pii


# ---------------------------------------------------------------------------
# SARIF output tests (patch86)
# ---------------------------------------------------------------------------

def test_sarif_output_valid_json_with_schema(pii_file: Path):
    """SARIF 출력이 올바른 JSON 이며 schema/version 필드가 정확하다."""
    result = scan_path(pii_file)
    sarif = scan_result_to_sarif(result)

    # Valid structure
    assert sarif["version"] == "2.1.0"
    assert "$schema" in sarif
    assert "sarif-schema-2.1.0" in sarif["$schema"]

    # runs array
    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "nufi-egress"
    assert run["tool"]["driver"]["version"] == "0.7.5"
    assert isinstance(run["tool"]["driver"]["rules"], list)
    assert len(run["tool"]["driver"]["rules"]) >= 1

    # Ensure it serializes to valid JSON
    serialized = json.dumps(sarif, ensure_ascii=False, indent=2)
    parsed = json.loads(serialized)
    assert parsed["version"] == "2.1.0"


def test_sarif_results_contain_expected_fields(tmp_path: Path):
    """SARIF results 에 ruleId, level, message, locations 필드가 포함된다."""
    # File with PII content (same format as pii_file fixture)
    f = tmp_path / "mixed.txt"
    f.write_text(
        "홍길동 주민번호 900101-1234567\n"
        "이메일: test@example.com\n",
        encoding="utf-8",
    )
    result = scan_path(f, check_injection=True)
    sarif = scan_result_to_sarif(result)

    run = sarif["runs"][0]
    results = run["results"]
    assert len(results) >= 1

    for r in results:
        # Required SARIF result fields
        assert "ruleId" in r
        assert "level" in r
        assert r["level"] in ("error", "warning", "note")
        assert "message" in r
        assert "text" in r["message"]
        assert "locations" in r
        assert len(r["locations"]) >= 1
        loc = r["locations"][0]
        assert "physicalLocation" in loc
        phys = loc["physicalLocation"]
        assert "artifactLocation" in phys
        assert "uri" in phys["artifactLocation"]
        assert "region" in phys
        assert "startLine" in phys["region"]
        assert phys["region"]["startLine"] >= 1
        assert "startColumn" in phys["region"]


# ---------------------------------------------------------------------------
# Redact mode tests (patch88)
# ---------------------------------------------------------------------------

def test_dry_run_shows_redactions_without_modifying(tmp_path: Path):
    """--dry-run 모드: 파일을 수정하지 않고 치환 대상만 보여준다."""
    f = tmp_path / "personal.txt"
    original = "김민수님 계좌 110-123-456789\n"
    f.write_text(original, encoding="utf-8")

    result = redact_path(f, dry_run=True)

    # Should report redactions
    assert result.total_redactions >= 1
    assert result.files_modified >= 1
    # File must NOT be modified
    assert f.read_text(encoding="utf-8") == original
    # No backups created
    assert result.backups_created == []


def test_redact_modifies_file_and_creates_backup(tmp_path: Path):
    """--redact 모드: PII 를 치환하고 .bak 백업을 생성한다."""
    f = tmp_path / "personal.txt"
    original = "김민수님 계좌 110-123-456789\n"
    f.write_text(original, encoding="utf-8")

    result = redact_path(f, dry_run=False, no_backup=False)

    # File should be modified
    modified = f.read_text(encoding="utf-8")
    assert modified != original
    assert "[REDACTED:" in modified
    # Backup should exist
    backup = Path(str(f) + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original
    # Result stats
    assert result.files_modified >= 1
    assert result.total_redactions >= 1
    assert len(result.backups_created) >= 1


def test_redact_no_backup_skips_backup_creation(tmp_path: Path):
    """--redact --no-backup: 백업 없이 파일을 수정한다."""
    f = tmp_path / "personal.txt"
    original = "홍길동 주민번호 900101-1234567\n"
    f.write_text(original, encoding="utf-8")

    result = redact_path(f, dry_run=False, no_backup=True)

    # File should be modified
    modified = f.read_text(encoding="utf-8")
    assert modified != original
    assert "[REDACTED:" in modified
    # No backup
    backup = Path(str(f) + ".bak")
    assert not backup.exists()
    assert result.backups_created == []
    assert result.total_redactions >= 1


# ---------------------------------------------------------------------------
# Stats output tests (patch91)
# ---------------------------------------------------------------------------

def test_stats_flag_prints_summary(pii_file: Path, capsys):
    """--stats 플래그: 엔티티별·위험도별 요약 통계를 출력한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=True,
    )
    rc = cmd_scan(args)
    assert rc == 0

    captured = capsys.readouterr()
    # Stats header must appear
    assert "스캔 요약" in captured.out or "Stats" in captured.out
    # Must show scanned file count
    assert "총 스캔 파일" in captured.out
    # Must show entity type breakdown
    assert "엔티티별" in captured.out
    # Must show risk breakdown
    assert "위험도별" in captured.out
    # At least one risk level shown
    assert any(level in captured.out for level in ("critical", "high", "medium", "low"))


# ---------------------------------------------------------------------------
# --output file tests (patch94)
# ---------------------------------------------------------------------------

def test_output_flag_writes_to_file(pii_file: Path, tmp_path: Path):
    """--output PATH: 스캔 결과를 파일에 JSON Lines 로 기록한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    out_file = tmp_path / "results.jsonl"
    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format=None,
        output=str(out_file),
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
    )
    rc = cmd_scan(args)
    assert rc == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    # Each non-empty line must be valid JSON
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) >= 1
    for line in lines:
        obj = json.loads(line)
        assert "file" in obj
        assert "line" in obj
        assert "entity_type" in obj
        assert "text" in obj
        assert "score" in obj


def test_format_jsonl_produces_valid_json_lines(pii_file: Path):
    """_render_jsonl: 각 줄이 유효한 JSON 객체인 JSON Lines 를 출력한다."""
    from enforcement.scan_cmd import _render_jsonl

    result = scan_path(pii_file)
    assert result.findings

    output = _render_jsonl(result)
    lines = [l for l in output.splitlines() if l.strip()]
    assert len(lines) >= 1
    for line in lines:
        obj = json.loads(line)
        assert "file" in obj
        assert "line" in obj
        assert "entity_type" in obj
        assert "text" in obj
        assert "score" in obj


# ---------------------------------------------------------------------------
# Parallel scan tests (patch97)
# ---------------------------------------------------------------------------

def test_parallel_scan_produces_same_results_as_sequential(tmp_path: Path):
    """--parallel N: 멀티스레드 스캔 결과가 순차 스캔과 동일하다."""
    # Create multiple files with PII
    for i in range(5):
        f = tmp_path / f"file_{i}.txt"
        f.write_text(f"사용자{i} 주민번호 900101-123456{i}\n", encoding="utf-8")

    # Sequential scan (parallel=1)
    seq_result = scan_path(tmp_path, parallel=1)

    # Parallel scan (parallel=4)
    par_result = scan_path(tmp_path, parallel=4)

    # Same number of files scanned
    assert par_result.files_scanned == seq_result.files_scanned
    # Same number of files with findings
    assert par_result.files_with_findings == seq_result.files_with_findings
    # Same total findings count
    assert len(par_result.findings) == len(seq_result.findings)
    # Same finding types (order may differ due to threading)
    seq_types = sorted((f.file, f.line, f.finding_type) for f in seq_result.findings)
    par_types = sorted((f.file, f.line, f.finding_type) for f in par_result.findings)
    assert par_types == seq_types


# ---------------------------------------------------------------------------
# Cache tests (patch101)
# ---------------------------------------------------------------------------

def test_cache_skips_unchanged_file(tmp_path: Path):
    """--cache: unchanged file is not re-scanned (cached findings returned)."""
    f = tmp_path / "data.txt"
    f.write_text("홍길동 주민번호 900101-1234567\n", encoding="utf-8")

    # First scan populates cache
    result1 = scan_path(tmp_path, cache=True)
    assert result1.files_scanned >= 1
    assert result1.has_pii
    findings_count = len(result1.findings)

    # Second scan should use cache — same findings returned
    result2 = scan_path(tmp_path, cache=True)
    assert result2.files_scanned >= 1
    assert result2.has_pii
    assert len(result2.findings) == findings_count

    # Verify cache file exists
    cache_file = tmp_path / ".nufi_cache.json"
    assert cache_file.exists()
    cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert str(f) in cache_data


def test_cache_invalidated_on_file_change(tmp_path: Path):
    """--cache: modified file is re-scanned (cache invalidated)."""
    f = tmp_path / "data.txt"
    f.write_text("홍길동 주민번호 900101-1234567\n", encoding="utf-8")

    # First scan populates cache
    result1 = scan_path(tmp_path, cache=True)
    assert result1.has_pii

    # Modify file to remove PII
    f.write_text("Nothing sensitive here.\n", encoding="utf-8")

    # Second scan should detect the change and re-scan
    result2 = scan_path(tmp_path, cache=True)
    assert not result2.has_pii
    assert len(result2.findings) == 0


# ---------------------------------------------------------------------------
# --summary-only tests (patch119)
# ---------------------------------------------------------------------------

def test_summary_only_flag_shows_compact_output(pii_file: Path, capsys):
    """--summary-only: per-file details hidden, only summary line printed."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format=None,
        output=None,
        fail_on_pii=True,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        summary_only=True,
    )
    rc = cmd_scan(args)
    # PII found → fail-on-pii → exit 1
    assert rc == 1

    captured = capsys.readouterr()
    # Summary line must contain key fields
    assert "Files scanned:" in captured.out
    assert "Findings:" in captured.out
    assert "Risk:" in captured.out
    assert "Status:" in captured.out
    # Must show FAIL since PII was found
    assert "FAIL" in captured.out
    # Must NOT contain per-file detail lines (no "L<number>:")
    lines = captured.out.strip().splitlines()
    assert len(lines) == 1  # exactly one summary line


# ---------------------------------------------------------------------------
# --verbose tests (patch137)
# ---------------------------------------------------------------------------

def test_verbose_flag_shows_detailed_output(pii_file: Path, capsys):
    """--verbose: 발견 항목별 상세 정보(컬럼/점수/탐지방법/컨텍스트)를 출력한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format=None,
        output=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        summary_only=False,
        verbose=True,
    )
    rc = cmd_scan(args)
    assert rc == 0

    captured = capsys.readouterr()
    out = captured.out
    # Must show scan summary header
    assert "Scan complete:" in out
    # Must show column info (C<number>)
    assert ":C" in out
    # Must show score
    assert "score=" in out
    # Must show detection method
    assert "method=" in out
    # Must show context line
    assert "context:" in out
    # Must show finding text line
    assert "text:" in out
    # Must show finding(s) count per file
    assert "finding(s)" in out


# ---------------------------------------------------------------------------
# --git-staged tests (patch171)
# ---------------------------------------------------------------------------

def test_git_staged_scans_only_staged_files(tmp_path: Path, capsys):
    """--git-staged: git staged 파일만 스캔한다 (모의 subprocess)."""
    import argparse
    import subprocess
    from unittest.mock import patch as mock_patch
    from enforcement.scan_cmd import cmd_scan, scan_staged, ScanResult, ScanFinding

    # Create a file with PII
    pii = tmp_path / "secret.txt"
    pii.write_text("홍길동 주민번호 900101-1234567\n", encoding="utf-8")

    # Create a file without PII (should not appear in findings)
    clean = tmp_path / "clean.txt"
    clean.write_text("Nothing sensitive here.\n", encoding="utf-8")

    # Mock _git_staged_files to return only the PII file
    staged_files = ["secret.txt"]

    def mock_run(cmd, **kwargs):
        """Mock subprocess.run for git diff --cached."""
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="\n".join(staged_files) + "\n", stderr=""
        )

    # Test scan_staged SDK function directly
    with mock_patch("enforcement.scan_cmd.subprocess.run", side_effect=mock_run):
        result = scan_staged(repo=str(tmp_path))

    assert result.files_scanned == 1
    assert result.has_pii
    assert len(result.findings) >= 1
    for f in result.findings:
        assert "secret.txt" in f.file

    # Test cmd_scan with --git-staged via mock of scan_staged
    with mock_patch("enforcement.scan_cmd.scan_staged") as mock_scan_staged:
        mock_result = ScanResult(
            files_scanned=1,
            files_with_findings=1,
            findings=[ScanFinding(
                file=str(pii), line=1, finding_type="PII:KR_RRN", text="900101-1234567"
            )],
        )
        mock_scan_staged.return_value = mock_result
        args = argparse.Namespace(
            target=None,
            pattern=None,
            check_injection=False,
            json=False,
            format=None,
            output=None,
            fail_on_pii=True,
            exclude=None,
            redact=False,
            dry_run=False,
            no_backup=False,
            stats=False,
            summary_only=False,
            verbose=False,
            git_staged=True,
            profile=None,
            clear_cache=False,
            parallel=1,
            cache=False,
        )
        rc = cmd_scan(args)
        assert rc == 1  # fail-on-pii should trigger
        mock_scan_staged.assert_called_once()


# ---------------------------------------------------------------------------
# False positive suppression tests (patch178)
# ---------------------------------------------------------------------------

def test_suppression_by_file_and_entity_type(pii_dir: Path):
    """file + entity_type 매칭으로 특정 파일의 특정 엔티티 발견을 억제한다."""
    # First, scan and confirm there are findings
    result = scan_path(pii_dir)
    assert result.has_pii
    original_count = len(result.findings)

    # Find a finding to suppress
    first_finding = result.findings[0]
    entity = first_finding.finding_type.split(":", 1)[1]
    rel_file = str(Path(first_finding.file).relative_to(pii_dir))

    # Create suppression file
    ignore_file = pii_dir / ".nufi_ignore_findings.yaml"
    ignore_file.write_text(
        f"suppressions:\n"
        f"  - file: \"{rel_file}\"\n"
        f"    entity_type: \"{entity}\"\n"
        f"    reason: \"Test suppression\"\n",
        encoding="utf-8",
    )

    # Re-scan and apply suppressions
    result2 = scan_path(pii_dir)
    suppressions = load_suppressions(ignore_file)
    suppressed = apply_suppressions(result2, suppressions, pii_dir)

    assert suppressed >= 1
    assert len(result2.findings) < original_count


def test_suppression_by_glob_pattern(pii_dir: Path):
    """pattern (glob) 매칭으로 파일명 패턴 기반 발견을 억제한다."""
    # Create a test file that matches a glob pattern
    test_file = pii_dir / "test_sample.txt"
    test_file.write_text("홍길동의 전화번호 010-9999-8888\n", encoding="utf-8")

    # Scan to confirm findings in test_sample.txt
    result = scan_path(pii_dir)
    test_findings = [f for f in result.findings if "test_sample.txt" in f.file]
    assert len(test_findings) >= 1

    # Create suppression with glob pattern
    ignore_file = pii_dir / ".nufi_ignore_findings.yaml"
    ignore_file.write_text(
        "suppressions:\n"
        "  - pattern: \"test_*\"\n"
        "    reason: \"All test files contain sample data\"\n",
        encoding="utf-8",
    )

    # Re-scan and apply suppressions
    result2 = scan_path(pii_dir)
    total_before = len(result2.findings)
    suppressions = load_suppressions(ignore_file)
    suppressed = apply_suppressions(result2, suppressions, pii_dir)

    # The test_sample.txt findings should be suppressed
    remaining_test = [f for f in result2.findings if "test_sample.txt" in f.file]
    assert len(remaining_test) == 0
    assert suppressed >= 1


# ---------------------------------------------------------------------------
# CSV format (patch180)
# ---------------------------------------------------------------------------

def test_format_csv_output(pii_file: Path):
    """--format csv 옵션: CSV 포맷으로 출력한다 (v0.7.0 헤더)."""
    import csv
    import io
    from enforcement.scan_cmd import _render_csv

    result = scan_path(pii_file)
    assert result.findings, "Test precondition: at least one finding"

    csv_text = _render_csv(result)
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # Header row — v0.7.0: entity_type,text,start,end,score
    assert rows[0] == ["entity_type", "text", "start", "end", "score"]
    # One data row per finding
    assert len(rows) == 1 + len(result.findings)
    # Check a data row has correct structure
    data_row = rows[1]
    assert data_row[0] != ""  # entity_type
    assert data_row[1] != ""  # text
    assert int(data_row[2]) >= 1  # start
    assert int(data_row[3]) > int(data_row[2])  # end > start
    assert float(data_row[4]) >= 0.0  # score


# ---------------------------------------------------------------------------
# --baseline tests (patch181)
# ---------------------------------------------------------------------------

def test_baseline_filters_known_findings(pii_file: Path, tmp_path: Path, capsys):
    """--baseline: 베이스라인에 있는 발견은 제외하고 신규만 보여준다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan, scan_path, _apply_baseline

    # First scan to create baseline
    result = scan_path(pii_file)
    assert result.has_pii

    # Write baseline as JSON
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Now scan with baseline — all findings are in baseline, so nothing new
    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format=None,
        output=None,
        fail_on_pii=True,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        parallel=1,
        cache=False,
        ignore_file=None,
        baseline=str(baseline_file),
        count_only=False,
    )
    rc = cmd_scan(args)
    # No new findings → exit 0 even with --fail-on-pii
    assert rc == 0

    captured = capsys.readouterr()
    assert "no findings" in captured.out.lower() or "0" in captured.out


# ---------------------------------------------------------------------------
# --count-only tests (patch182)
# ---------------------------------------------------------------------------

def test_count_only_prints_summary(pii_file: Path, capsys):
    """--count-only: 발견 건수만 출력하고 상세 없음."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format=None,
        output=None,
        fail_on_pii=True,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        parallel=1,
        cache=False,
        ignore_file=None,
        baseline=None,
        count_only=True,
    )
    rc = cmd_scan(args)
    # PII found + --fail-on-pii + count > 0 → exit 1
    assert rc == 1

    captured = capsys.readouterr()
    assert "Found:" in captured.out
    assert "PII findings" in captured.out
    assert "files" in captured.out


# ---------------------------------------------------------------------------
# --min-score tests (patch186)
# ---------------------------------------------------------------------------

def test_min_score_filters_low_confidence_findings(pii_file: Path, capsys):
    """--min-score: 낮은 신뢰도 발견을 필터링한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    # First verify findings exist without min-score filter
    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=True,
        format=None,
        output=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        parallel=1,
        cache=False,
        ignore_file=None,
        baseline=None,
        count_only=False,
        min_score=0.0,
    )
    rc = cmd_scan(args)
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    all_count = data["summary"]["total"]
    assert all_count > 0

    # Now with impossibly high min-score — should filter all findings
    args.min_score = 99.0
    rc = cmd_scan(args)
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["summary"]["total"] == 0


# ---------------------------------------------------------------------------
# --only-types tests (patch188)
# ---------------------------------------------------------------------------

def test_only_types_filters_to_specified_entities(pii_file: Path, capsys):
    """--only-types: 지정한 엔티티 타입만 보고한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    # First scan without filter to see all findings
    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=True,
        format=None,
        output=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        parallel=1,
        cache=False,
        ignore_file=None,
        baseline=None,
        count_only=False,
        min_score=0.0,
        only_types=None,
    )
    rc = cmd_scan(args)
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    all_count = data["summary"]["total"]
    assert all_count > 0

    # Get all entity types found
    all_types = set()
    for f in data["findings"]:
        all_types.add(f["entity_type"].upper())

    # Now filter to a non-existent type — should return 0 findings
    args.only_types = "NONEXISTENT_TYPE"
    rc = cmd_scan(args)
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["summary"]["total"] == 0

    # Filter to the actual types found — should return same count
    args.only_types = ",".join(all_types)
    rc = cmd_scan(args)
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["summary"]["total"] == all_count


# ---------------------------------------------------------------------------
# v0.7.0 — --format json|sarif|csv 출력 포맷 다양화 테스트
# ---------------------------------------------------------------------------

def test_format_json_schema(pii_file: Path, capsys):
    """--format json: version, scan_target, findings[], summary 스키마 검증."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format="json",
        output=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        parallel=1,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        cache=False,
        ignore_file=None,
        baseline=None,
        count_only=False,
        min_score=0.0,
        only_types=None,
        pseudonymize=False,
    )
    rc = cmd_scan(args)
    assert rc == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    # Top-level fields
    assert "version" in data
    assert "scan_target" in data
    assert "findings" in data
    assert "summary" in data

    # Version matches VERSION file
    assert data["version"] == "0.7.5"
    assert data["scan_target"] == str(pii_file)

    # Findings array
    assert isinstance(data["findings"], list)
    assert len(data["findings"]) >= 1
    for f in data["findings"]:
        assert "entity_type" in f
        assert "text" in f
        assert "start" in f
        assert "end" in f
        assert "score" in f
        assert isinstance(f["start"], int)
        assert isinstance(f["end"], int)
        assert f["end"] > f["start"]

    # Summary
    assert data["summary"]["total"] == len(data["findings"])
    assert isinstance(data["summary"]["by_type"], dict)
    assert sum(data["summary"]["by_type"].values()) == data["summary"]["total"]


def test_format_json_flag_alias(pii_file: Path, capsys):
    """--json 플래그가 --format json 과 동일한 구조화 JSON 을 출력한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=True,
        format=None,
        output=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        parallel=1,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        cache=False,
        ignore_file=None,
        baseline=None,
        count_only=False,
        min_score=0.0,
        only_types=None,
        pseudonymize=False,
    )
    rc = cmd_scan(args)
    assert rc == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "version" in data
    assert "findings" in data
    assert "summary" in data


def test_format_sarif_v2_schema(pii_file: Path):
    """SARIF 출력이 v2.1.0 스키마를 준수하고 driver.name 이 nufi-egress 이다."""
    result = scan_path(pii_file)
    sarif = scan_result_to_sarif(result)

    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "nufi-egress"
    assert len(run["results"]) >= 1
    for r in run["results"]:
        assert "ruleId" in r
        assert "level" in r
        assert "message" in r
        assert "locations" in r


def test_format_csv_v070_headers(pii_file: Path):
    """--format csv: entity_type,text,start,end,score 헤더로 출력한다."""
    import csv
    import io
    from enforcement.scan_cmd import _render_csv

    result = scan_path(pii_file)
    assert result.findings, "Test precondition: at least one finding"

    csv_text = _render_csv(result)
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # Header row — v0.7.0 spec
    assert rows[0] == ["entity_type", "text", "start", "end", "score"]
    assert len(rows) == 1 + len(result.findings)

    # Data rows
    for row in rows[1:]:
        assert len(row) == 5
        assert int(row[2]) >= 1  # start
        assert int(row[3]) > int(row[2])  # end > start
        assert float(row[4]) >= 0.0  # score


def test_format_csv_via_cmd(pii_file: Path, capsys):
    """cmd_scan --format csv 로 CSV 출력이 정상 동작한다."""
    import argparse
    from enforcement.scan_cmd import cmd_scan

    args = argparse.Namespace(
        target=str(pii_file),
        pattern=None,
        check_injection=False,
        json=False,
        format="csv",
        output=None,
        fail_on_pii=False,
        exclude=None,
        redact=False,
        dry_run=False,
        no_backup=False,
        stats=False,
        parallel=1,
        summary_only=False,
        verbose=False,
        git_staged=False,
        profile=None,
        clear_cache=False,
        cache=False,
        ignore_file=None,
        baseline=None,
        count_only=False,
        min_score=0.0,
        only_types=None,
        pseudonymize=False,
    )
    rc = cmd_scan(args)
    assert rc == 0

    import csv
    import io
    captured = capsys.readouterr()
    reader = csv.reader(io.StringIO(captured.out))
    rows = list(reader)
    assert rows[0] == ["entity_type", "text", "start", "end", "score"]
    assert len(rows) >= 2


# ---------------------------------------------------------------------------
# Recursive scan tests (v0.7.4)
# ---------------------------------------------------------------------------

@pytest.fixture()
def recursive_dir(tmp_path: Path) -> Path:
    """디렉터리 재귀 스캔용 테스트 구조."""
    (tmp_path / "root.txt").write_text("이메일: test@example.com\n", encoding="utf-8")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "deep.txt").write_text("주민번호 900101-1234567\n", encoding="utf-8")
    deep = sub / "nested"
    deep.mkdir()
    (deep / "more.txt").write_text("전화번호 010-1234-5678\n", encoding="utf-8")
    return tmp_path


def test_recursive_scan_finds_pii_in_all_subdirs(recursive_dir: Path):
    """--recursive 로 하위 디렉터리까지 모든 PII 를 탐지한다."""
    rec = scan_recursive(recursive_dir)
    assert rec.summary.files_scanned >= 3
    assert rec.summary.files_with_pii >= 2
    assert len(rec.files) >= 2
    # entity counts populated
    assert len(rec.summary.entity_counts) >= 1
    total = sum(rec.summary.entity_counts.values())
    assert total >= 2


def test_recursive_scan_skips_binary(tmp_path: Path):
    """바이너리 파일은 건너뛴다."""
    (tmp_path / "text.txt").write_text("이메일: a@b.com\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03" * 200)
    rec = scan_recursive(tmp_path)
    assert rec.summary.files_skipped >= 1
    # binary file should not appear in scanned results
    scanned_files = {fe["file"] for fe in rec.files}
    assert not any("binary.bin" in f for f in scanned_files)


def test_recursive_scan_exclude_filter(recursive_dir: Path):
    """--exclude 패턴이 파일을 제외한다."""
    rec = scan_recursive(recursive_dir, exclude=["subdir/*"])
    # subdir 내 파일이 제외되므로 scanned 수가 줄어야 함
    scanned_files = {fe["file"] for fe in rec.files}
    assert not any("deep.txt" in f for f in scanned_files)


def test_recursive_scan_include_filter(recursive_dir: Path):
    """--include 패턴에 매칭되는 파일만 스캔한다."""
    rec = scan_recursive(recursive_dir, include=["*.txt"])
    assert rec.summary.files_scanned >= 1
    # Only .txt files should be scanned
    all_finding_files = {fe["file"] for fe in rec.files}
    for f in all_finding_files:
        assert f.endswith(".txt")


def test_recursive_scan_empty_dir(tmp_path: Path):
    """빈 디렉터리 → 빈 결과."""
    rec = scan_recursive(tmp_path)
    assert rec.summary.files_scanned == 0
    assert rec.summary.files_with_pii == 0
    assert len(rec.files) == 0
    assert len(rec.summary.entity_counts) == 0
    assert len(rec.summary.top_files) == 0


def test_recursive_scan_aggregate_report_accuracy(recursive_dir: Path):
    """집계 리포트의 수치가 정확하다."""
    rec = scan_recursive(recursive_dir)
    # files_with_pii should match len(rec.files)
    assert rec.summary.files_with_pii == len(rec.files)
    # total entity counts should match sum of all findings
    total_findings = sum(len(fe["findings"]) for fe in rec.files)
    total_entity = sum(rec.summary.entity_counts.values())
    assert total_entity == total_findings
    # top_files should be <= 5
    assert len(rec.summary.top_files) <= 5


def test_recursive_scan_top_files_order(tmp_path: Path):
    """Top 파일이 발견 건수 내림차순이다."""
    # File with many PII
    (tmp_path / "many.txt").write_text(
        "email1@a.com email2@b.com email3@c.com\n900101-1234567\n",
        encoding="utf-8",
    )
    (tmp_path / "few.txt").write_text("just one: test@x.com\n", encoding="utf-8")
    rec = scan_recursive(tmp_path)
    if len(rec.summary.top_files) >= 2:
        assert rec.summary.top_files[0]["count"] >= rec.summary.top_files[1]["count"]


def test_recursive_scan_json_output(recursive_dir: Path):
    """JSON 출력에 files[], summary 가 포함된다."""
    from enforcement.scan_cmd import _render_recursive_json
    rec = scan_recursive(recursive_dir)
    out = _render_recursive_json(rec, target=str(recursive_dir))
    doc = json.loads(out)
    assert "version" in doc
    assert "files" in doc
    assert "summary" in doc
    assert "files_scanned" in doc["summary"]
    assert "files_skipped" in doc["summary"]
    assert "files_with_pii" in doc["summary"]
    assert "entity_counts" in doc["summary"]
    assert "top_files" in doc["summary"]


def test_recursive_scan_csv_output(recursive_dir: Path):
    """CSV 출력에 file, line, entity_type, text, score 컬럼이 있다."""
    import csv
    import io
    from enforcement.scan_cmd import _render_recursive_csv
    rec = scan_recursive(recursive_dir)
    out = _render_recursive_csv(rec)
    reader = csv.reader(io.StringIO(out))
    rows = list(reader)
    assert rows[0] == ["file", "line", "entity_type", "text", "score"]
    assert len(rows) >= 2
