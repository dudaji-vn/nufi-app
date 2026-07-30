"""``nufi-egress playground`` -- interactive PII analysis REPL (patch145).

Starts an interactive loop where each input line is analysed via
``inspect_text`` and a concise one-line summary is printed.

Special commands inside the REPL:
  quit / exit   Exit the playground.
  help          Show usage hints.
  mode inspect  Default mode -- show PII findings + risk + routing.
  mode mask     Show masked output (PII replaced with ***).
  mode redact   Show redacted output (PII replaced with [TYPE] tags).

Non-interactive usage (pipe / ``--text``):
  echo "주민번호 900101-1234568" | nufi-egress playground
  nufi-egress playground --text "주민번호 900101-1234568"
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional


def _use_emoji(args=None) -> bool:
    """Return False when emoji output should be suppressed."""
    if args is not None and getattr(args, "no_emoji", False):
        return False
    return os.environ.get("NUFI_NO_EMOJI", "") not in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Compact single-line renderer
# ---------------------------------------------------------------------------

def _render_compact(result: dict, *, emoji: bool = True) -> str:
    """One-line summary: [PII] entities | [Risk] level | [Route] | [Block]."""
    parts: List[str] = []

    # PII entities
    pii = result.get("pii_findings") or []
    if pii:
        entities = " | ".join(
            f"{f['entity_type']}: {f['text']}" for f in pii
        )
        parts.append(f"[PII] {entities}")
    else:
        parts.append("[PII] none")

    # Injection
    inj = result.get("injection_findings") or []
    if inj:
        inj_str = ", ".join(f["severity"] for f in inj)
        parts.append(f"[Injection] {inj_str}")

    # Risk
    risk = result.get("risk_level", "clean")
    parts.append(f"[Risk] {risk}")

    # Route
    routing = result.get("routing", "cloud")
    if emoji:
        route_icon = "\U0001f512" if routing == "local" else "\u2601\ufe0f"
    else:
        route_icon = "[L]" if routing == "local" else "[C]"
    parts.append(f"[Route] {route_icon} {routing}")

    # Block
    blocked = result.get("blocked", False)
    if emoji:
        block_icon = "\u26d4" if blocked else "\u2705"
    else:
        block_icon = "[!]" if blocked else "[OK]"
    block_text = "yes" if blocked else "no"
    parts.append(f"[Block] {block_icon} {block_text}")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Process a single line
# ---------------------------------------------------------------------------

def _process_line(text: str, mode: str, *, emoji: bool = True) -> str:
    """Analyse *text* and return a formatted string based on *mode*."""
    if mode == "inspect":
        from enforcement.inspect_cmd import inspect_text
        result = inspect_text(text)
        return _render_compact(result, emoji=emoji)
    elif mode in ("mask", "redact"):
        from enforcement.transform_cmd import _transform_text
        return _transform_text(text, mode)
    else:
        return f"[error] unknown mode: {mode}"


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
NuFi Playground -- interactive PII analysis REPL

Type any text to analyse it. Special commands:
  quit / exit   Exit the playground.
  help          Show this message.
  mode inspect  Show PII findings + risk + routing (default).
  mode mask     Show masked output (PII → ***).
  mode redact   Show redacted output (PII → [TYPE])."""


def _run_repl(*, emoji: bool = True) -> int:
    """Interactive REPL loop.  Returns exit code."""
    mode = "inspect"
    print("NuFi Playground (type 'quit' to exit)")
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        stripped = line.strip()
        if not stripped:
            continue

        # Special commands
        low = stripped.lower()
        if low in ("quit", "exit"):
            break
        if low == "help":
            print(_HELP_TEXT)
            continue
        if low.startswith("mode "):
            new_mode = low.split(None, 1)[1]
            if new_mode in ("inspect", "mask", "redact"):
                mode = new_mode
                print(f"[mode] switched to {mode}")
            else:
                print(f"[error] unknown mode '{new_mode}'. Use: inspect, mask, redact")
            continue

        # Normal input → process
        print(_process_line(stripped, mode, emoji=emoji))

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_playground(args) -> int:
    """``nufi-egress playground`` CLI handler."""
    emoji = _use_emoji(args)
    text: Optional[str] = getattr(args, "text", None)

    # Non-interactive: --text flag
    if text:
        mode = getattr(args, "mode", None) or "inspect"
        print(_process_line(text, mode, emoji=emoji))
        return 0

    # Non-interactive: piped stdin (not a TTY)
    if not sys.stdin.isatty():
        mode = getattr(args, "mode", None) or "inspect"
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line.strip():
                print(_process_line(line.strip(), mode, emoji=emoji))
        return 0

    # Interactive REPL
    return _run_repl(emoji=emoji)
