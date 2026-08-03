"""tests/test_cmp342_profile_summary.py -- scan --profile + scan --summary 테스트 (v0.7.7 / CMP-342).

시나리오:
1. 각 내장 프로파일 동작 검증 (strict, standard, minimal, financial)
2. 커스텀 프로파일 로딩 검증 (nufi.yaml)
3. summary 출력 검증 (stderr dashboard + JSON summary)
4. 프로파일 + 개별옵션 혼용 검증
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

import pytest

from enforcement.scan_profiles import (
    ScanProfile,
    apply_profile_to_args,
    load_profiles,
    resolve_profile,
    _load_profiles_from_file,
)
from enforcement.scan_cmd import (
    ScanResult,
    ScanFinding,
    _render_json,
    _render_summary_dashboard,
    _build_summary_dict,
    cmd_scan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(finding_type: str = "PII:KR_RRN", text: str = "900101-1234568",
                  score: float = 0.99, file: str = "test.txt", line: int = 1) -> ScanFinding:
    return ScanFinding(
        file=file, line=line, finding_type=finding_type, text=text, score=score,
    )


def _make_result(findings: list[ScanFinding] | None = None, files_scanned: int = 5) -> ScanResult:
    findings = findings or []
    files_with = len(set(f.file for f in findings))
    return ScanResult(
        files_scanned=files_scanned,
        files_with_findings=files_with,
        findings=findings,
    )


def _pii_file(tmp_path: Path, name: str = "data.txt") -> Path:
    """Create a file with PII content for scanning."""
    f = tmp_path / name
    f.write_text(
        "주민번호: 900101-1234568\n"
        "카드번호: 4111111111111111\n"
        "이메일: test@example.com\n"
        "계좌: 110-123-456789\n",
        encoding="utf-8",
    )
    return f


# ===========================================================================
# 1. 내장 프로파일 동작 검증
# ===========================================================================

class TestBuiltinProfiles:
    """각 내장 프로파일이 올바르게 로딩되고 설정이 적용되는지 검증."""

    def test_strict_profile(self):
        profile = resolve_profile("strict")
        assert profile.name == "strict"
        assert profile.min_score == 0.5
        assert profile.fail_on_pii is True
        assert profile.only_types is None  # all types

    def test_standard_profile(self):
        profile = resolve_profile("standard")
        assert profile.name == "standard"
        assert profile.min_score == 0.7
        assert profile.fail_on_pii is False
        assert "KR_RRN" in profile.only_types
        assert "CREDIT_CARD" in profile.only_types
        assert "KR_ACCOUNT" in profile.only_types
        assert "EMAIL" in profile.only_types

    def test_minimal_profile(self):
        profile = resolve_profile("minimal")
        assert profile.name == "minimal"
        assert profile.min_score == 0.9
        assert "KR_RRN" in profile.only_types
        assert "CREDIT_CARD" in profile.only_types
        # Should NOT include KR_ACCOUNT or EMAIL
        assert "KR_ACCOUNT" not in profile.only_types
        assert "EMAIL" not in profile.only_types

    def test_financial_profile(self):
        profile = resolve_profile("financial")
        assert profile.name == "financial"
        assert profile.min_score == 0.7
        assert profile.fail_on_pii is True
        assert "KR_ACCOUNT" in profile.only_types
        assert "CREDIT_CARD" in profile.only_types
        assert "KR_RRN" in profile.only_types

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError, match="Unknown scan profile"):
            resolve_profile("nonexistent")

    def test_all_builtin_profiles_loadable(self):
        profiles = load_profiles()
        for name in ("strict", "standard", "minimal", "financial", "development", "ci"):
            assert name in profiles, f"Built-in profile '{name}' missing"


class TestProfileApplyToArgs:
    """프로파일 설정이 argparse Namespace에 올바르게 적용되는지 검증."""

    def test_standard_profile_sets_only_types_and_min_score(self):
        args = SimpleNamespace(
            only_types=None, min_score=0.0, fail_on_pii=False,
            check_injection=False, parallel=1, format=None,
            pattern=None, exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("standard")
        apply_profile_to_args(profile, args)
        assert args.only_types == "KR_RRN,CREDIT_CARD,KR_ACCOUNT,EMAIL"
        assert args.min_score == 0.7

    def test_explicit_option_overrides_profile(self):
        """개별 옵션이 프로파일보다 우선해야 함."""
        args = SimpleNamespace(
            only_types="KR_RRN",  # explicitly set
            min_score=0.8,  # explicitly set
            fail_on_pii=True,
            check_injection=False, parallel=1, format=None,
            pattern=None, exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("standard")
        apply_profile_to_args(profile, args)
        # Explicit values should NOT be overridden
        assert args.only_types == "KR_RRN"
        assert args.min_score == 0.8
        assert args.fail_on_pii is True  # was already True

    def test_strict_profile_sets_fail_on_pii(self):
        args = SimpleNamespace(
            only_types=None, min_score=0.0, fail_on_pii=False,
            check_injection=False, parallel=1, format=None,
            pattern=None, exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("strict")
        apply_profile_to_args(profile, args)
        assert args.fail_on_pii is True
        assert args.min_score == 0.5

    def test_financial_profile_applies(self):
        args = SimpleNamespace(
            only_types=None, min_score=0.0, fail_on_pii=False,
            check_injection=False, parallel=1, format=None,
            pattern=None, exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("financial")
        apply_profile_to_args(profile, args)
        assert args.fail_on_pii is True
        assert "KR_ACCOUNT" in args.only_types
        assert args.min_score == 0.7


# ===========================================================================
# 2. 커스텀 프로파일 로딩 검증
# ===========================================================================

class TestCustomProfiles:
    """nufi.yaml 에서 커스텀 프로파일 로딩 검증."""

    def test_load_custom_profile_from_nufi_yaml(self, tmp_path: Path):
        nufi_yaml = tmp_path / "nufi.yaml"
        nufi_yaml.write_text(
            "scan_profiles:\n"
            "  my_custom:\n"
            "    only_types: 'EMAIL,KR_PHONE'\n"
            "    min_score: 0.6\n"
            "    fail_on_pii: true\n",
            encoding="utf-8",
        )
        profiles = _load_profiles_from_file(nufi_yaml)
        assert "my_custom" in profiles
        assert profiles["my_custom"]["only_types"] == "EMAIL,KR_PHONE"
        assert profiles["my_custom"]["min_score"] == 0.6

    def test_custom_profile_resolves(self, tmp_path: Path):
        nufi_yaml = tmp_path / "nufi.yaml"
        nufi_yaml.write_text(
            "scan_profiles:\n"
            "  hipaa:\n"
            "    only_types: 'EMAIL,KR_RRN'\n"
            "    min_score: 0.4\n"
            "    fail_on_pii: true\n",
            encoding="utf-8",
        )
        profiles = _load_profiles_from_file(nufi_yaml)
        profile = resolve_profile("hipaa", profiles=profiles)
        assert profile.name == "hipaa"
        assert profile.only_types == "EMAIL,KR_RRN"
        assert profile.min_score == 0.4
        assert profile.fail_on_pii is True

    def test_empty_nufi_yaml_returns_empty(self, tmp_path: Path):
        nufi_yaml = tmp_path / "nufi.yaml"
        nufi_yaml.write_text("", encoding="utf-8")
        profiles = _load_profiles_from_file(nufi_yaml)
        assert profiles == {}

    def test_nonexistent_nufi_yaml_returns_empty(self, tmp_path: Path):
        profiles = _load_profiles_from_file(tmp_path / "nufi.yaml")
        assert profiles == {}

    def test_invalid_key_raises(self, tmp_path: Path):
        nufi_yaml = tmp_path / "nufi.yaml"
        nufi_yaml.write_text(
            "scan_profiles:\n"
            "  bad:\n"
            "    invalid_key: true\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unknown keys"):
            _load_profiles_from_file(nufi_yaml)


# ===========================================================================
# 3. summary 출력 검증
# ===========================================================================

class TestSummaryDashboard:
    """--summary 집계 대시보드 출력 검증."""

    def test_summary_dashboard_outputs_to_stderr(self):
        """_render_summary_dashboard는 stderr로 출력해야 함."""
        findings = [
            _make_finding("PII:KR_RRN", score=0.99),
            _make_finding("PII:CREDIT_CARD", text="4111111111111111", score=0.95, file="b.txt"),
            _make_finding("PII:EMAIL", text="test@example.com", score=0.8, file="c.txt"),
        ]
        result = _make_result(findings)

        buf = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = buf
        try:
            _render_summary_dashboard(result)
        finally:
            sys.stderr = old_stderr

        output = buf.getvalue()
        assert "NuFi Scan Summary Dashboard" in output
        assert "KR_RRN" in output
        assert "CREDIT_CARD" in output
        assert "EMAIL" in output
        # Should contain ASCII bar characters
        assert "█" in output

    def test_summary_dashboard_empty_result(self):
        """빈 결과에서도 대시보드가 출력되어야 함."""
        result = _make_result([])

        buf = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = buf
        try:
            _render_summary_dashboard(result)
        finally:
            sys.stderr = old_stderr

        output = buf.getvalue()
        assert "NuFi Scan Summary Dashboard" in output
        assert "0 findings" in output

    def test_summary_dashboard_severity_distribution(self):
        """심각도 분포가 올바르게 표시되어야 함."""
        findings = [
            _make_finding("PII:KR_RRN"),  # strong PII -> critical
            _make_finding("PII:EMAIL", text="a@b.com"),  # non-strong -> high
        ]
        result = _make_result(findings)

        buf = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = buf
        try:
            _render_summary_dashboard(result)
        finally:
            sys.stderr = old_stderr

        output = buf.getvalue()
        assert "critical" in output or "high" in output

    def test_build_summary_dict(self):
        """_build_summary_dict가 올바른 구조를 반환하는지 검증."""
        findings = [
            _make_finding("PII:KR_RRN"),
            _make_finding("PII:KR_RRN", file="b.txt"),
            _make_finding("PII:CREDIT_CARD", text="4111111111111111"),
        ]
        result = _make_result(findings)
        summary = _build_summary_dict(result)

        assert summary["total_findings"] == 3
        assert summary["by_type"]["KR_RRN"] == 2
        assert summary["by_type"]["CREDIT_CARD"] == 1
        assert "by_severity" in summary
        assert summary["files_scanned"] == 5

    def test_json_output_with_summary_flag(self):
        """--format json --summary 시 summary 필드에 by_severity 포함."""
        findings = [
            _make_finding("PII:KR_RRN"),
            _make_finding("PII:CREDIT_CARD", text="4111111111111111"),
        ]
        result = _make_result(findings)

        json_str = _render_json(result, target="test", summary=True)
        doc = json.loads(json_str)

        assert "summary" in doc
        assert "by_severity" in doc["summary"]
        assert "files_scanned" in doc["summary"]
        assert "files_with_findings" in doc["summary"]
        assert doc["summary"]["total"] == 2

    def test_json_output_without_summary_flag(self):
        """--format json (without --summary) 시 기존 summary 형식 유지."""
        findings = [_make_finding("PII:KR_RRN")]
        result = _make_result(findings)

        json_str = _render_json(result, target="test", summary=False)
        doc = json.loads(json_str)

        assert "summary" in doc
        assert "by_severity" not in doc["summary"]
        assert doc["summary"]["total"] == 1


# ===========================================================================
# 4. 프로파일 + 개별옵션 혼용 검증
# ===========================================================================

class TestProfileWithOverrides:
    """프로파일과 개별 옵션 혼용 시 개별 옵션이 우선하는지 검증."""

    def test_profile_min_score_overridden_by_cli(self):
        args = SimpleNamespace(
            only_types=None, min_score=0.95,  # CLI override
            fail_on_pii=False, check_injection=False,
            parallel=1, format=None, pattern=None,
            exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("standard")  # min_score=0.7
        apply_profile_to_args(profile, args)
        assert args.min_score == 0.95  # CLI wins

    def test_profile_only_types_overridden_by_cli(self):
        args = SimpleNamespace(
            only_types="KR_RRN",  # CLI override
            min_score=0.0, fail_on_pii=False,
            check_injection=False, parallel=1, format=None,
            pattern=None, exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("standard")  # only_types includes more
        apply_profile_to_args(profile, args)
        assert args.only_types == "KR_RRN"  # CLI wins

    def test_profile_fail_on_pii_not_overridden_when_false(self):
        """프로파일에서 fail_on_pii=True, CLI에서 미지정(False) → 프로파일 값 적용."""
        args = SimpleNamespace(
            only_types=None, min_score=0.0, fail_on_pii=False,
            check_injection=False, parallel=1, format=None,
            pattern=None, exclude=None, cache=False, stats=False,
        )
        profile = resolve_profile("financial")  # fail_on_pii=True
        apply_profile_to_args(profile, args)
        assert args.fail_on_pii is True

    def test_profile_parallel_overridden_by_cli(self):
        args = SimpleNamespace(
            only_types=None, min_score=0.0, fail_on_pii=False,
            check_injection=False, parallel=8,  # CLI override
            format=None, pattern=None, exclude=None,
            cache=False, stats=False,
        )
        profile = resolve_profile("strict")  # parallel=4
        apply_profile_to_args(profile, args)
        assert args.parallel == 8  # CLI wins


# ===========================================================================
# 5. cmd_scan 통합 — profile + summary 실제 스캔 동작
# ===========================================================================

class TestCmdScanIntegration:
    """cmd_scan() 에서 --profile, --summary 가 함께 작동하는지 검증."""

    def test_scan_with_standard_profile(self, tmp_path: Path):
        """--profile standard 로 스캔 시 주요 엔티티만 필터링."""
        _pii_file(tmp_path)
        args = SimpleNamespace(
            target=str(tmp_path / "data.txt"),
            profile="standard", summary=False, summary_only=False,
            verbose=False, stats=False, json=False, format="json",
            output=None, fail_on_pii=False, check_injection=False,
            pattern=None, exclude=None, parallel=1, cache=False,
            redact=False, dry_run=False, no_backup=False,
            git_staged=False, ignore_file=None, baseline=None,
            count_only=False, min_score=0.0, only_types=None,
            pseudonymize=False, watch=False, watch_interval=1.0,
            diff=None, recursive=False, include=None,
            clear_cache=False,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_scan(args)
        assert rc == 0
        doc = json.loads(buf.getvalue())
        # standard profile: only KR_RRN, CREDIT_CARD, KR_ACCOUNT, EMAIL
        for f in doc["findings"]:
            assert f["entity_type"] in ("KR_RRN", "CREDIT_CARD", "KR_ACCOUNT", "EMAIL")

    def test_scan_with_summary_json(self, tmp_path: Path):
        """--format json --summary 시 summary에 by_severity 포함."""
        _pii_file(tmp_path)
        args = SimpleNamespace(
            target=str(tmp_path / "data.txt"),
            profile=None, summary=True, summary_only=False,
            verbose=False, stats=False, json=False, format="json",
            output=None, fail_on_pii=False, check_injection=False,
            pattern=None, exclude=None, parallel=1, cache=False,
            redact=False, dry_run=False, no_backup=False,
            git_staged=False, ignore_file=None, baseline=None,
            count_only=False, min_score=0.0, only_types=None,
            pseudonymize=False, watch=False, watch_interval=1.0,
            diff=None, recursive=False, include=None,
            clear_cache=False,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_scan(args)
        assert rc == 0
        doc = json.loads(buf.getvalue())
        assert "by_severity" in doc["summary"]
        assert "files_scanned" in doc["summary"]

    def test_scan_with_minimal_profile_high_threshold(self, tmp_path: Path):
        """--profile minimal 은 min_score=0.9, KR_RRN+CREDIT_CARD만 스캔."""
        _pii_file(tmp_path)
        args = SimpleNamespace(
            target=str(tmp_path / "data.txt"),
            profile="minimal", summary=False, summary_only=False,
            verbose=False, stats=False, json=False, format="json",
            output=None, fail_on_pii=False, check_injection=False,
            pattern=None, exclude=None, parallel=1, cache=False,
            redact=False, dry_run=False, no_backup=False,
            git_staged=False, ignore_file=None, baseline=None,
            count_only=False, min_score=0.0, only_types=None,
            pseudonymize=False, watch=False, watch_interval=1.0,
            diff=None, recursive=False, include=None,
            clear_cache=False,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_scan(args)
        assert rc == 0
        doc = json.loads(buf.getvalue())
        # minimal: only KR_RRN + CREDIT_CARD, score >= 0.9
        for f in doc["findings"]:
            assert f["entity_type"] in ("KR_RRN", "CREDIT_CARD")
            assert f["score"] >= 0.9

    def test_scan_with_financial_profile_fail_on_pii(self, tmp_path: Path):
        """--profile financial 은 PII 발견 시 exit 1."""
        _pii_file(tmp_path)
        args = SimpleNamespace(
            target=str(tmp_path / "data.txt"),
            profile="financial", summary=False, summary_only=False,
            verbose=False, stats=False, json=False, format="text",
            output=None, fail_on_pii=False, check_injection=False,
            pattern=None, exclude=None, parallel=1, cache=False,
            redact=False, dry_run=False, no_backup=False,
            git_staged=False, ignore_file=None, baseline=None,
            count_only=False, min_score=0.0, only_types=None,
            pseudonymize=False, watch=False, watch_interval=1.0,
            diff=None, recursive=False, include=None,
            clear_cache=False,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_scan(args)
        # financial profile sets fail_on_pii=True, and data.txt has PII
        assert rc == 1


# ===========================================================================
# 6. ScanProfile dataclass 검증
# ===========================================================================

class TestScanProfileDataclass:
    """ScanProfile to_dict 가 새 필드를 포함하는지 검증."""

    def test_to_dict_includes_new_fields(self):
        p = ScanProfile(
            name="test", only_types="KR_RRN,EMAIL", min_score=0.8,
        )
        d = p.to_dict()
        assert d["only_types"] == "KR_RRN,EMAIL"
        assert d["min_score"] == 0.8

    def test_to_dict_defaults(self):
        p = ScanProfile(name="default")
        d = p.to_dict()
        assert d["only_types"] is None
        assert d["min_score"] is None
