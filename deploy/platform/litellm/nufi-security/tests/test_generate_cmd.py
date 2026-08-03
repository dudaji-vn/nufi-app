"""Tests for ``nufi-egress generate`` sample data generator (patch131)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from enforcement.generate_cmd import generate_samples, cmd_generate


class TestGenerateSamples:
    """Unit tests for the generate_samples function."""

    def test_default_count(self):
        samples = generate_samples()
        assert len(samples) == 10

    def test_custom_count(self):
        samples = generate_samples(count=5, seed=42)
        assert len(samples) == 5

    def test_sample_structure(self):
        samples = generate_samples(count=3, seed=42)
        for s in samples:
            assert isinstance(s.text, str) and len(s.text) > 0
            assert isinstance(s.entity_types, list) and len(s.entity_types) > 0
            assert s.severity in ("low", "medium", "high", "critical")
            assert s.language in ("ko", "en")

    def test_deterministic_with_seed(self):
        s1 = generate_samples(count=5, seed=123)
        s2 = generate_samples(count=5, seed=123)
        assert [s.text for s in s1] == [s.text for s in s2]

    def test_include_injection(self):
        samples_no_inj = generate_samples(count=3, include_injection=False, seed=1)
        samples_with_inj = generate_samples(count=3, include_injection=True, seed=1)
        # With injection adds extra samples beyond the PII count
        assert len(samples_with_inj) > len(samples_no_inj)
        # Check that injection samples have PROMPT_INJECTION entity type
        inj_samples = samples_with_inj[3:]
        assert all("PROMPT_INJECTION" in s.entity_types for s in inj_samples)

    def test_to_dict(self):
        samples = generate_samples(count=1, seed=42)
        d = samples[0].to_dict()
        assert set(d.keys()) == {"text", "entity_types", "severity", "language"}


class TestCmdGenerate:
    """Integration tests for the CLI handler."""

    def test_jsonl_output_to_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "samples.jsonl"

            class Args:
                count = 3
                include_injection = False
                format = "jsonl"
                output = str(out)
                seed = 42

            rc = cmd_generate(Args())
            assert rc == 0
            assert out.exists()
            lines = out.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 3
            for line in lines:
                obj = json.loads(line)
                assert "text" in obj
                assert "entity_types" in obj

    def test_text_format_to_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "samples.txt"

            class Args:
                count = 2
                include_injection = False
                format = "text"
                output = str(out)
                seed = 42

            rc = cmd_generate(Args())
            assert rc == 0
            lines = out.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2
            # Text format should NOT be valid JSON
            for line in lines:
                try:
                    json.loads(line)
                    is_json = True
                except json.JSONDecodeError:
                    is_json = False
                assert not is_json, "text format should not produce JSON lines"
