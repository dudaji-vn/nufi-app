"""CMP-271: config/pii_routing.yaml 설정 파일 도입 테스트.

YAML 설정 파일 로딩 및 PiiRouter 통합을 검증한다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from gateway.pii_router import PiiRouter, load_pii_routing_config, ROUTE_REASON_CLEAN


# ── load_pii_routing_config ──


class TestLoadConfig:
    """설정 파일 로딩."""

    def test_load_valid_config(self, tmp_path):
        cfg_file = tmp_path / "pii_routing.yaml"
        cfg_file.write_text(yaml.dump({
            "enabled": True,
            "local_model": "my-local",
            "cloud_model": "my-cloud",
            "fail_closed": False,
            "force_local_entities": ["KR_RRN", "SECRET"],
        }))
        cfg = load_pii_routing_config(str(cfg_file))
        assert cfg["enabled"] is True
        assert cfg["local_model"] == "my-local"
        assert cfg["cloud_model"] == "my-cloud"
        assert cfg["fail_closed"] is False
        assert cfg["force_local_entities"] == ["KR_RRN", "SECRET"]

    def test_load_missing_file(self, tmp_path):
        cfg = load_pii_routing_config(str(tmp_path / "nonexistent.yaml"))
        assert cfg == {}

    def test_load_empty_file(self, tmp_path):
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("")
        cfg = load_pii_routing_config(str(cfg_file))
        assert cfg == {}

    def test_load_default_config(self):
        """기본 경로(config/pii_routing.yaml) 로드 성공."""
        cfg = load_pii_routing_config()
        assert cfg["enabled"] is True
        assert cfg["local_model"] == "nufi-local"
        assert cfg["cloud_model"] == "nufi-cloud"
        assert cfg["fail_closed"] is True

    def test_env_override(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text(yaml.dump({"local_model": "env-model"}))
        monkeypatch.setenv("NUFI_PII_ROUTING_CONFIG", str(cfg_file))
        cfg = load_pii_routing_config()
        assert cfg["local_model"] == "env-model"


# ── PiiRouter config integration ──


class TestPiiRouterConfig:
    """PiiRouter 가 config 파일을 읽어 초기화."""

    def test_from_config(self, tmp_path):
        cfg_file = tmp_path / "pii_routing.yaml"
        cfg_file.write_text(yaml.dump({
            "enabled": True,
            "local_model": "cfg-local",
            "cloud_model": "cfg-cloud",
            "fail_closed": False,
            "force_local_entities": ["KR_RRN"],
        }))
        router = PiiRouter.from_config(str(cfg_file))
        assert router.local_model == "cfg-local"
        assert router.cloud_model == "cfg-cloud"
        assert router.fail_closed is False
        assert router.force_local_entities == {"KR_RRN"}
        assert router.enabled is True

    def test_from_config_override(self, tmp_path):
        """kwargs 가 config 값을 오버라이드."""
        cfg_file = tmp_path / "pii_routing.yaml"
        cfg_file.write_text(yaml.dump({
            "local_model": "cfg-local",
            "cloud_model": "cfg-cloud",
        }))
        router = PiiRouter.from_config(str(cfg_file), local_model="override-local")
        assert router.local_model == "override-local"
        assert router.cloud_model == "cfg-cloud"

    def test_enabled_false_skips_detection(self, tmp_path):
        """enabled: false 이면 PII 감지 없이 클라우드 허용."""
        cfg_file = tmp_path / "pii_routing.yaml"
        cfg_file.write_text(yaml.dump({"enabled": False}))
        router = PiiRouter.from_config(str(cfg_file))
        assert router.enabled is False
        decision = router.route("주민번호 900101-1234568")
        assert not decision.routed_to_local
        assert decision.reason == ROUTE_REASON_CLEAN

    def test_force_local_entities_from_config(self, tmp_path):
        """config 의 force_local_entities 적용."""
        cfg_file = tmp_path / "pii_routing.yaml"
        cfg_file.write_text(yaml.dump({
            "force_local_entities": ["KR_RRN"],
        }))
        router = PiiRouter.from_config(str(cfg_file))
        # 이메일만 → 클라우드 (KR_RRN 아님)
        d1 = router.route("user@example.com 으로 보내세요")
        assert not d1.routed_to_local
        # 주민번호 → 로컬
        d2 = router.route("주민번호 900101-1234568")
        assert d2.routed_to_local

    def test_default_init_reads_config(self):
        """기본 생성자도 config/pii_routing.yaml 을 읽는다."""
        router = PiiRouter()
        assert router.enabled is True
        assert router.local_model == "nufi-local"
        assert router.cloud_model == "nufi-cloud"
        assert router.fail_closed is True

    def test_explicit_params_override_config(self, tmp_path):
        """명시적 파라미터가 config 보다 우선."""
        cfg_file = tmp_path / "pii_routing.yaml"
        cfg_file.write_text(yaml.dump({
            "local_model": "cfg-local",
            "cloud_model": "cfg-cloud",
        }))
        router = PiiRouter(
            local_model="explicit-local",
            cloud_model="explicit-cloud",
            config_path=str(cfg_file),
        )
        assert router.local_model == "explicit-local"
        assert router.cloud_model == "explicit-cloud"
