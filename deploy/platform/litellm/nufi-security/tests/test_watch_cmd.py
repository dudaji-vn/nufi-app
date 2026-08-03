"""tests/test_watch_cmd.py — nufi-egress watch 커맨드 테스트 (patch92, patch102).

시나리오:
1. --once 모드: PII 포함 파일 탐지 → exit 1 + ALERT 출력
2. --once 모드: 클린 파일만 → exit 0 + no findings 메시지
3. --webhook URL: PII 탐지 시 JSON payload POST
"""
from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import List

import pytest

from enforcement.watch_cmd import watch_directory


@pytest.fixture()
def pii_dir(tmp_path: Path) -> Path:
    """PII 가 포함된 파일이 있는 디렉터리."""
    f = tmp_path / "secret.txt"
    f.write_text("홍길동 주민번호 900101-1234567\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def clean_dir(tmp_path: Path) -> Path:
    """PII 없는 클린 디렉터리."""
    f = tmp_path / "hello.txt"
    f.write_text("Hello world, nothing sensitive here.\n", encoding="utf-8")
    return tmp_path


class TestWatchOnceDetectsPII:
    """--once mode detects PII in new file."""

    def test_once_finds_pii(self, pii_dir: Path, capsys):
        rc = watch_directory(pii_dir, once=True)
        assert rc == 1
        captured = capsys.readouterr()
        assert "[ALERT]" in captured.out
        assert "PII:" in captured.out

    def test_once_finds_pii_with_pattern(self, pii_dir: Path, capsys):
        rc = watch_directory(pii_dir, once=True, patterns=["*.txt"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "[ALERT]" in captured.out


class TestWatchOnceCleanExit:
    """--once mode with clean files exits cleanly."""

    def test_once_clean_exit(self, clean_dir: Path, capsys):
        rc = watch_directory(clean_dir, once=True)
        assert rc == 0
        captured = capsys.readouterr()
        assert "no findings" in captured.out

    def test_once_respects_nufiignore(self, tmp_path: Path, capsys):
        """Files matching .nufiignore patterns are skipped."""
        # Create a file with PII
        f = tmp_path / "data.txt"
        f.write_text("주민번호 900101-1234567\n", encoding="utf-8")
        # Create .nufiignore that excludes it
        ignore = tmp_path / ".nufiignore"
        ignore.write_text("data.txt\n", encoding="utf-8")

        rc = watch_directory(tmp_path, once=True)
        assert rc == 0
        captured = capsys.readouterr()
        assert "[ALERT]" not in captured.out


# ---------------------------------------------------------------------------
# Webhook tests (patch102)
# ---------------------------------------------------------------------------

class _WebhookHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler that collects POST payloads."""

    received: List[bytes] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.received_payloads.append(body)  # type: ignore[attr-defined]
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress log output during tests


class TestWatchWebhook:
    """--webhook URL posts JSON on PII detection."""

    def test_webhook_posts_payload_on_pii(self, tmp_path: Path, capsys):
        """When PII is detected, a JSON payload is POSTed to the webhook URL."""
        # Start a local HTTP server
        server = HTTPServer(("127.0.0.1", 0), _WebhookHandler)
        server.received_payloads = []  # type: ignore[attr-defined]
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        # Create a file with PII
        f = tmp_path / "secret.txt"
        f.write_text("홍길동 주민번호 900101-1234567\n", encoding="utf-8")

        webhook_url = f"http://127.0.0.1:{port}/hook"
        rc = watch_directory(tmp_path, once=True, webhook=webhook_url)
        assert rc == 1

        thread.join(timeout=5)
        server.server_close()

        # Verify payload was received
        assert len(server.received_payloads) >= 1  # type: ignore[attr-defined]
        payload = json.loads(server.received_payloads[0])  # type: ignore[attr-defined]
        assert payload["event"] == "pii_detected"
        assert "file" in payload
        assert "findings" in payload
        assert len(payload["findings"]) >= 1
        assert "timestamp" in payload
