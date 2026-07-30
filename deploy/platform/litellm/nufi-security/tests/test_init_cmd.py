"""Tests for `nufi-egress init` quick-start command (patch90)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from enforcement.init_cmd import run_init


class TestInitCreatesFiles:
    """init creates expected files in an empty directory."""

    def test_creates_all_expected_files(self, tmp_path: Path):
        # Also create a .git dir so hook install can work
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        result = run_init(target_dir=str(tmp_path), install_hook=True)

        assert result["errors"] == []
        assert result["skipped"] == []

        # Check config files
        assert (tmp_path / "config" / "policy.yaml").exists()
        assert (tmp_path / "config" / "pii_routing.yaml").exists()
        assert (tmp_path / "config" / "injection_patterns.yaml").exists()
        assert (tmp_path / ".nufiignore").exists()
        assert (tmp_path / ".git" / "hooks" / "pre-commit").exists()

        # Verify config contents are valid YAML-ish (start with comment or key)
        policy = (tmp_path / "config" / "policy.yaml").read_text()
        assert "version:" in policy
        assert "entities:" in policy

        routing = (tmp_path / "config" / "pii_routing.yaml").read_text()
        assert "enabled:" in routing

        patterns = (tmp_path / "config" / "injection_patterns.yaml").read_text()
        assert "patterns:" in patterns

        ignore = (tmp_path / ".nufiignore").read_text()
        assert "node_modules/" in ignore

        # Hook is executable
        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        assert os.access(hook, os.X_OK)

        # Created list includes all files
        assert len(result["created"]) == 5

    def test_creates_without_hook(self, tmp_path: Path):
        result = run_init(target_dir=str(tmp_path), install_hook=False)

        assert result["errors"] == []
        assert len(result["created"]) == 4
        assert (tmp_path / "config" / "policy.yaml").exists()
        assert (tmp_path / ".nufiignore").exists()


class TestInitSkipsExisting:
    """init skips existing files without error (idempotent)."""

    def test_skips_existing_files(self, tmp_path: Path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        # First run — creates everything
        result1 = run_init(target_dir=str(tmp_path), install_hook=True)
        assert result1["errors"] == []
        assert len(result1["created"]) == 5
        assert result1["skipped"] == []

        # Capture original content
        original_policy = (tmp_path / "config" / "policy.yaml").read_text()

        # Modify a file to prove it's not overwritten
        (tmp_path / "config" / "policy.yaml").write_text("# custom\n")

        # Second run — skips everything
        result2 = run_init(target_dir=str(tmp_path), install_hook=True)
        assert result2["errors"] == []
        assert result2["created"] == []
        assert len(result2["skipped"]) == 5

        # Verify file was NOT overwritten
        assert (tmp_path / "config" / "policy.yaml").read_text() == "# custom\n"

    def test_partial_existing(self, tmp_path: Path):
        # Only policy.yaml exists
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "policy.yaml").write_text("# existing\n")

        result = run_init(target_dir=str(tmp_path), install_hook=False)

        assert result["errors"] == []
        assert "config/policy.yaml" in result["skipped"]
        # Other files should be created
        assert (tmp_path / "config" / "pii_routing.yaml").exists()
        assert (tmp_path / ".nufiignore").exists()
        assert len(result["created"]) == 3
