"""tests/test_config_cmd.py -- nufi-egress config validate/show 테스트 (patch105, patch187, patch208-209).

시나리오:
1. 유효한 설정 → 에러 없음
2. 잘못된 regex 패턴 → 에러 보고
3. config show → 유효 설정 반환(defaults 적용)
4. pii_routing.yaml 없는 부분 config → warning, 나머지 정상 검증
5. injection_patterns.yaml 빈/잘못된 YAML → 에러 보고
6. policy.yaml required 키(default_action) 누락 → 에러 보고
7. config version 불일치 확인
8. show_config default 머징: 커스텀 값이 기본값을 올바르게 오버라이드
9. injection_patterns.yaml에 custom_patterns가 list가 아닌 경우 → 에러
10. policy.yaml에 잘못된 entity action → warning
"""
from __future__ import annotations

from pathlib import Path

import pytest

from enforcement.config_cmd import validate_config, show_config, ConfigValidationResult


class TestValidConfigNoErrors:
    """유효한 설정 파일 → 에러 없음."""

    def test_valid_config(self, tmp_path: Path):
        # Create valid config files
        (tmp_path / "policy.yaml").write_text(
            "version: 1\n"
            "default_action: warn\n"
            "blocking_actions: [block]\n"
            "entities:\n"
            "  KR_RRN:\n"
            "    action: block\n"
            "    severity: critical\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\n"
            "local_model: nufi-local\n"
            "cloud_model: nufi-cloud\n",
            encoding="utf-8",
        )
        (tmp_path / "injection_patterns.yaml").write_text(
            "custom_patterns:\n"
            "  - pattern: 'hello.*world'\n"
            "    severity: low\n"
            "    description: test\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        assert result.files_checked == 3
        assert not result.has_errors


class TestInvalidRegexReported:
    """injection_patterns.yaml 에 잘못된 regex → 에러 보고."""

    def test_invalid_regex(self, tmp_path: Path):
        # Create config with invalid regex
        (tmp_path / "policy.yaml").write_text(
            "version: 1\ndefault_action: warn\nentities: {}\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: x\ncloud_model: y\n",
            encoding="utf-8",
        )
        (tmp_path / "injection_patterns.yaml").write_text(
            "custom_patterns:\n"
            "  - pattern: '[invalid(regex'\n"
            "    severity: high\n"
            "    description: bad pattern\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        assert result.has_errors
        # Should have at least one error about invalid regex
        regex_errors = [
            i for i in result.issues
            if "invalid regex" in i.message.lower() or "regex" in i.message.lower()
        ]
        assert len(regex_errors) >= 1


class TestConfigShow:
    """config show — 유효 설정 반환 (patch187)."""

    def test_show_with_existing_files(self, tmp_path: Path):
        """Existing config files are loaded and defaults are merged."""
        (tmp_path / "policy.yaml").write_text(
            "version: 2\ndefault_action: block\nentities:\n  KR_RRN:\n    action: block\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: my-local\ncloud_model: my-cloud\n",
            encoding="utf-8",
        )
        # No injection_patterns.yaml or scan_profiles.yaml → defaults used

        effective = show_config(config_dir=tmp_path)

        # policy loaded from file
        assert effective["policy"]["version"] == 2
        assert effective["policy"]["default_action"] == "block"
        assert "KR_RRN" in effective["policy"]["entities"]

        # pii_routing loaded from file
        assert effective["pii_routing"]["enabled"] is True
        assert effective["pii_routing"]["local_model"] == "my-local"

        # injection_patterns falls back to defaults (file missing)
        assert effective["injection_patterns"]["custom_patterns"] == []

        # scan_profiles falls back to defaults (file missing)
        assert effective["scan_profiles"]["profiles"] == {}

        # Meta
        assert effective["_meta"]["config_dir"] == str(tmp_path)
        assert len(effective["_meta"]["files_loaded"]) == 2  # only 2 files exist


class TestPartialConfigMissingPiiRouting:
    """pii_routing.yaml 없는 부분 config → warning 발생, 나머지 정상 검증 (patch208)."""

    def test_missing_pii_routing(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 1\ndefault_action: warn\nentities: {}\n",
            encoding="utf-8",
        )
        # pii_routing.yaml 없음
        (tmp_path / "injection_patterns.yaml").write_text(
            "custom_patterns: []\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        assert result.files_checked == 2  # policy + injection_patterns only
        # pii_routing missing → warning
        routing_warnings = [
            i for i in result.issues
            if "pii_routing" in i.file and i.severity == "warning"
        ]
        assert len(routing_warnings) == 1
        assert not result.has_errors


class TestEmptyInjectionPatternsYaml:
    """injection_patterns.yaml 빈 파일 → YAML parse 결과 None → root-not-mapping 에러 (patch208)."""

    def test_empty_yaml(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 1\ndefault_action: warn\nentities: {}\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: x\ncloud_model: y\n",
            encoding="utf-8",
        )
        # Empty YAML file → yaml.safe_load returns None
        (tmp_path / "injection_patterns.yaml").write_text("", encoding="utf-8")

        result = validate_config(config_dir=tmp_path)
        assert result.has_errors
        mapping_errors = [
            i for i in result.issues
            if "mapping" in i.message.lower() or "root" in i.message.lower()
        ]
        assert len(mapping_errors) >= 1


class TestMalformedInjectionPatternsYaml:
    """injection_patterns.yaml 잘못된 YAML 구문 → parse 에러 (patch208)."""

    def test_malformed_yaml(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 1\ndefault_action: warn\nentities: {}\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: x\ncloud_model: y\n",
            encoding="utf-8",
        )
        # Invalid YAML syntax
        (tmp_path / "injection_patterns.yaml").write_text(
            "custom_patterns:\n  - pattern: hello\n  bad indent\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        parse_errors = [
            i for i in result.issues
            if "parse" in i.message.lower() or "yaml" in i.message.lower()
        ]
        assert len(parse_errors) >= 1


class TestMissingRequiredKeyDefaultAction:
    """policy.yaml에 default_action 키 누락 → 에러 보고 (patch208)."""

    def test_missing_default_action(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 1\nentities: {}\n",  # default_action missing
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: x\ncloud_model: y\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        assert result.has_errors
        missing_field = [
            i for i in result.issues
            if "default_action" in i.message
        ]
        assert len(missing_field) == 1


class TestConfigVersionInShowConfig:
    """show_config에서 config version 값이 올바르게 반영되는지 확인 (patch208)."""

    def test_version_from_file(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 3\ndefault_action: block\nentities: {}\n",
            encoding="utf-8",
        )

        effective = show_config(config_dir=tmp_path)
        assert effective["policy"]["version"] == 3

    def test_version_default_when_missing(self, tmp_path: Path):
        """policy.yaml 없을 때 기본 version 1."""
        effective = show_config(config_dir=tmp_path)
        assert effective["policy"]["version"] == 1


class TestDefaultMergingOverride:
    """커스텀 값이 기본값을 올바르게 오버라이드하는지 확인 (patch208)."""

    def test_custom_overrides_defaults(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 5\ndefault_action: block\nblocking_actions: [block, redact]\n"
            "entities:\n  EMAIL:\n    action: redact\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: custom-local\ncloud_model: custom-cloud\n",
            encoding="utf-8",
        )

        effective = show_config(config_dir=tmp_path)

        # policy: custom values override defaults
        assert effective["policy"]["version"] == 5
        assert effective["policy"]["default_action"] == "block"
        assert effective["policy"]["blocking_actions"] == ["block", "redact"]
        assert "EMAIL" in effective["policy"]["entities"]

        # pii_routing: custom values override defaults
        assert effective["pii_routing"]["enabled"] is True
        assert effective["pii_routing"]["local_model"] == "custom-local"
        assert effective["pii_routing"]["cloud_model"] == "custom-cloud"

        # injection_patterns: no file → full defaults
        assert effective["injection_patterns"]["custom_patterns"] == []

    def test_partial_override_preserves_defaults(self, tmp_path: Path):
        """파일에 일부 키만 있으면 나머지는 기본값 유지."""
        (tmp_path / "policy.yaml").write_text(
            "version: 2\ndefault_action: warn\nentities: {}\n",
            encoding="utf-8",
        )

        effective = show_config(config_dir=tmp_path)
        # blocking_actions not in file → default preserved
        assert effective["policy"]["blocking_actions"] == ["block"]


class TestInjectionPatternsNotList:
    """custom_patterns가 list가 아닌 경우 → 에러 (patch208)."""

    def test_custom_patterns_not_list(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 1\ndefault_action: warn\nentities: {}\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: x\ncloud_model: y\n",
            encoding="utf-8",
        )
        (tmp_path / "injection_patterns.yaml").write_text(
            "custom_patterns: not-a-list\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        assert result.has_errors
        list_errors = [
            i for i in result.issues
            if "list" in i.message.lower()
        ]
        assert len(list_errors) >= 1


class TestInvalidEntityAction:
    """policy.yaml에 잘못된 entity action → warning (patch208)."""

    def test_unknown_action_warning(self, tmp_path: Path):
        (tmp_path / "policy.yaml").write_text(
            "version: 1\ndefault_action: warn\n"
            "entities:\n  KR_RRN:\n    action: destroy\n",
            encoding="utf-8",
        )
        (tmp_path / "pii_routing.yaml").write_text(
            "enabled: true\nlocal_model: x\ncloud_model: y\n",
            encoding="utf-8",
        )

        result = validate_config(config_dir=tmp_path)
        action_warnings = [
            i for i in result.issues
            if "unknown action" in i.message.lower()
        ]
        assert len(action_warnings) == 1
        assert action_warnings[0].severity == "warning"
