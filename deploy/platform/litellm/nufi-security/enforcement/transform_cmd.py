"""``nufi-egress mask`` / ``nufi-egress redact`` — 텍스트 변환 명령 (patch124).

인라인 텍스트(--text) 또는 파일(--file)의 PII를 마스킹/리댁션하여 출력한다.

- mask: PII를 asterisk(*)로 가림  (예: 김민수 → ***)
- redact: PII를 타입 태그로 교체  (예: 김민수 → [KR_PERSON])

scan --redact(파일 인플레이스 재작성)와 달리 stdout 출력 전용이며 원본을 수정하지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from egress_audit.pipeline import DetectionPipeline
from egress_audit.pseudonymize import mask as _mask_value


def _transform_text(text: str, mode: str) -> str:
    """Transform a single text string by masking or redacting PII.

    Args:
        text: Input text to transform.
        mode: "mask" for asterisk masking, "redact" for type-tagged replacement.

    Returns:
        Transformed text.
    """
    pipeline = DetectionPipeline()
    findings = pipeline.analyze(text)

    # Filter out non-PII findings (e.g. PROMPT_INJECTION)
    pii_findings = [f for f in findings if f.entity_type not in ("PROMPT_INJECTION",)]

    if not pii_findings:
        return text

    # Sort by start position descending for safe in-place replacement
    pii_findings.sort(key=lambda f: f.start, reverse=True)

    result = text
    for f in pii_findings:
        if mode == "mask":
            replacement = _mask_value(f.text)
        else:  # redact
            replacement = f"[{f.entity_type}]"
        result = result[:f.start] + replacement + result[f.end:]

    return result


def cmd_mask(args) -> int:
    """``nufi-egress mask`` CLI handler."""
    return _run_transform(args, mode="mask")


def cmd_redact(args) -> int:
    """``nufi-egress redact`` CLI handler."""
    return _run_transform(args, mode="redact")


def _run_transform(args, *, mode: str) -> int:
    """Shared handler for mask/redact commands."""
    text: Optional[str] = getattr(args, "text", None)
    file_path: Optional[str] = getattr(args, "file", None)
    output_path: Optional[str] = getattr(args, "output", None)

    if not text and not file_path:
        print(f"오류: --text 또는 --file 을 지정해야 합니다.", file=sys.stderr)
        return 1

    if text:
        transformed = _transform_text(text, mode)
    else:
        # File mode: read file, transform each line
        p = Path(file_path)  # type: ignore[arg-type]
        if not p.exists():
            print(f"오류: 파일을 찾을 수 없습니다: {file_path}", file=sys.stderr)
            return 1
        lines = p.read_text(encoding="utf-8").splitlines()
        transformed_lines = [_transform_text(line, mode) for line in lines]
        transformed = "\n".join(transformed_lines)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(transformed + "\n", encoding="utf-8")
        print(f"[{mode}] 결과 기록: {output_path}", file=sys.stderr)
    else:
        print(transformed)

    return 0
