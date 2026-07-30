"""tests/test_cmp341_init_doctor.py -- init 프로젝트 설정 생성기 + doctor 자가진단 강화 (v0.7.6 / CMP-341).

시나리오:
1. init: 기본 설정 생성 검증 (nufi.yaml, .pre-commit-config.yaml, policy 등)
2. init --ci github: GitHub Actions 워크플로우 생성 검증
3. init --ci gitlab: GitLab CI 파이프라인 생성 검증
4. init --dry-run: 미리보기 출력 검증 (파일 미생성)
5. doctor: 신규 체크항목 검증 (python, dependencies, nufi_yaml, git_hook, model_files)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from enforcement.init_cmd import run_init, render_result


# ===========================================================================
# init tests
# ===========================================================================

class TestInitDefault:
    """init: 기본 설정 생성 (nufi.yaml 포함)."""

    def test_creates_nufi_yaml(self, tmp_path: Path):
        """nufi.yaml 이 생성된다."""
        result = run_init(target_dir=str(tmp_path))
        assert not result["errors"]
        assert (tmp_path / "nufi.yaml").exists()
        assert "nufi.yaml" in result["created"]

    def test_creates_pre_commit_config(self, tmp_path: Path):
        """.pre-commit-config.yaml 이 생성된다."""
        result = run_init(target_dir=str(tmp_path))
        assert not result["errors"]
        assert (tmp_path / ".pre-commit-config.yaml").exists()
        content = (tmp_path / ".pre-commit-config.yaml").read_text()
        assert "nufi-scan" in content

    def test_creates_policy_yaml(self, tmp_path: Path):
        """config/policy.yaml 이 생성된다."""
        result = run_init(target_dir=str(tmp_path))
        assert not result["errors"]
        assert (tmp_path / "config" / "policy.yaml").exists()

    def test_creates_nufiignore(self, tmp_path: Path):
        """.nufiignore 이 생성된다."""
        result = run_init(target_dir=str(tmp_path))
        assert not result["errors"]
        assert (tmp_path / ".nufiignore").exists()

    def test_idempotent(self, tmp_path: Path):
        """두 번 실행해도 기존 파일을 덮어쓰지 않는다."""
        run_init(target_dir=str(tmp_path))
        result2 = run_init(target_dir=str(tmp_path))
        assert not result2["errors"]
        assert not result2["created"]
        assert len(result2["skipped"]) > 0

    def test_pre_commit_append_existing(self, tmp_path: Path):
        """.pre-commit-config.yaml 가 이미 있으면 nufi hook 을 append."""
        existing_content = "repos:\n  - repo: https://example.com\n    hooks:\n      - id: example\n"
        pre_commit = tmp_path / ".pre-commit-config.yaml"
        pre_commit.write_text(existing_content, encoding="utf-8")

        result = run_init(target_dir=str(tmp_path))
        assert not result["errors"]
        content = pre_commit.read_text()
        assert "nufi-scan" in content
        assert "example" in content  # original content preserved
        assert any("append" in c for c in result["created"])

    def test_pre_commit_skip_if_nufi_exists(self, tmp_path: Path):
        """이미 nufi-scan 이 있는 .pre-commit-config.yaml 은 건드리지 않는다."""
        existing_content = "repos:\n  - repo: local\n    hooks:\n      - id: nufi-scan\n"
        pre_commit = tmp_path / ".pre-commit-config.yaml"
        pre_commit.write_text(existing_content, encoding="utf-8")

        result = run_init(target_dir=str(tmp_path))
        assert not result["errors"]
        assert ".pre-commit-config.yaml" in result["skipped"]


class TestInitCIGithub:
    """init --ci github: GitHub Actions 워크플로우 생성."""

    def test_creates_github_workflow(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), ci="github")
        assert not result["errors"]
        wf = tmp_path / ".github" / "workflows" / "nufi-scan.yml"
        assert wf.exists()
        content = wf.read_text()
        assert "nufi-egress guard --ci" in content
        assert "actions/checkout" in content

    def test_github_workflow_in_created(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), ci="github")
        assert any("nufi-scan.yml" in c for c in result["created"])


class TestInitCIGitlab:
    """init --ci gitlab: GitLab CI 파이프라인 생성."""

    def test_creates_gitlab_ci(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), ci="gitlab")
        assert not result["errors"]
        ci_file = tmp_path / ".gitlab-ci.yml"
        assert ci_file.exists()
        content = ci_file.read_text()
        assert "nufi-egress guard --ci" in content
        assert "merge_request_event" in content


class TestInitDryRun:
    """init --dry-run: 미리보기만, 파일 미생성."""

    def test_no_files_created(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), dry_run=True)
        assert result["dry_run"] is True
        assert len(result["created"]) > 0
        # Verify no files were actually created
        assert not (tmp_path / "nufi.yaml").exists()
        assert not (tmp_path / "config").exists()
        assert not (tmp_path / ".pre-commit-config.yaml").exists()

    def test_dry_run_lists_files(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), dry_run=True)
        assert "nufi.yaml" in result["created"]
        assert any("policy.yaml" in c for c in result["created"])

    def test_dry_run_with_ci(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), ci="github", dry_run=True)
        assert any("nufi-scan.yml" in c for c in result["created"])
        assert not (tmp_path / ".github").exists()

    def test_dry_run_render(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), dry_run=True)
        text = render_result(result)
        assert "[dry-run]" in text
        assert "Would create:" in text


# ===========================================================================
# doctor tests (new checks from CMP-341)
# ===========================================================================

class TestDoctorPythonVersion:
    """doctor: Python 버전 호환성 체크."""

    def test_python_version_pass(self):
        from enforcement.doctor import check_python_version, DoctorContext, PASS
        ctx = DoctorContext()
        result = check_python_version(ctx)
        # We're running Python ≥3.9 in this test environment
        assert result.status == PASS
        assert "python_version" in result.data


class TestDoctorDependencies:
    """doctor: 필수 의존성 설치 상태 체크."""

    def test_dependencies_check(self):
        from enforcement.doctor import check_dependencies, DoctorContext, PASS
        ctx = DoctorContext()
        result = check_dependencies(ctx)
        # yaml (PyYAML) and core modules should be installed
        assert result.status == PASS
        assert "installed" in result.data
        assert "yaml" in result.data["installed"]


class TestDoctorNufiYaml:
    """doctor: nufi.yaml 유효성 체크."""

    def test_nufi_yaml_missing(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_nufi_yaml, DoctorContext, WARN
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        ctx = DoctorContext()
        result = check_nufi_yaml(ctx)
        assert result.status == WARN
        assert not result.data["exists"]

    def test_nufi_yaml_valid(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_nufi_yaml, DoctorContext, PASS
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        nufi_yaml = tmp_path / "nufi.yaml"
        nufi_yaml.write_text("version: 1\nscan:\n  exclude: ['*.pyc']\n", encoding="utf-8")
        ctx = DoctorContext()
        result = check_nufi_yaml(ctx)
        assert result.status == PASS
        assert result.data["valid"]

    def test_nufi_yaml_invalid(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_nufi_yaml, DoctorContext, FAIL
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        nufi_yaml = tmp_path / "nufi.yaml"
        nufi_yaml.write_text("{{invalid yaml", encoding="utf-8")
        ctx = DoctorContext()
        result = check_nufi_yaml(ctx)
        assert result.status == FAIL


class TestDoctorGitHook:
    """doctor: git hook 설치 상태 체크."""

    def test_no_git_repo(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_git_hook, DoctorContext, WARN
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        ctx = DoctorContext()
        result = check_git_hook(ctx)
        assert result.status == WARN
        assert not result.data["git_repo"]

    def test_git_repo_no_hook(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_git_hook, DoctorContext, WARN
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        ctx = DoctorContext()
        result = check_git_hook(ctx)
        assert result.status == WARN


class TestDoctorModelFiles:
    """doctor: 모델 파일 존재·무결성 체크."""

    def test_no_models_dir(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_model_files, DoctorContext, WARN
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        ctx = DoctorContext()
        result = check_model_files(ctx)
        assert result.status == WARN
        assert not result.data["models_dir_exists"]

    def test_empty_models_dir(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_model_files, DoctorContext, WARN
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        (tmp_path / "models").mkdir()
        ctx = DoctorContext()
        result = check_model_files(ctx)
        assert result.status == WARN
        assert result.data["onnx_count"] == 0

    def test_valid_onnx_file(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_model_files, DoctorContext, PASS
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        models = tmp_path / "models"
        models.mkdir()
        onnx = models / "test.onnx"
        onnx.write_bytes(b"\x08\x06\x12\x04test")  # 4+ bytes
        ctx = DoctorContext()
        result = check_model_files(ctx)
        assert result.status == PASS
        assert result.data["onnx_count"] == 1

    def test_empty_onnx_file(self, tmp_path: Path, monkeypatch):
        from enforcement import doctor
        from enforcement.doctor import check_model_files, DoctorContext, FAIL
        monkeypatch.setattr(doctor, "_ROOT", tmp_path)
        models = tmp_path / "models"
        models.mkdir()
        onnx = models / "test.onnx"
        onnx.write_bytes(b"")
        ctx = DoctorContext()
        result = check_model_files(ctx)
        assert result.status == FAIL


class TestDoctorFormat:
    """doctor --format text|json 출력 포맷 지원."""

    def test_format_json(self):
        from enforcement.doctor import main
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--format", "json"])
        output = buf.getvalue()
        # Should be valid JSON
        parsed = json.loads(output)
        assert "checks" in parsed
        assert "summary" in parsed

    def test_format_text(self):
        from enforcement.doctor import main
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--format", "text"])
        output = buf.getvalue()
        assert "nufi doctor" in output
        # Should NOT have JSON block
        assert "--- JSON ---" not in output
