"""``nufi-egress pseudonymize`` — 가역 가명화 / 원복 CLI 커맨드.

텍스트 또는 파일의 PII를 가역적 surrogate 토큰(⟦P1⟧ 등)으로 치환하고,
세션 ID를 통해 원복할 수 있다.

- pseudonymize: PII → surrogate 치환 + 세션 ID 발급
- pseudonymize --restore: surrogate → 원본 복원
- --file / --output: 파일 단위 처리
- --json / --format json: JSON 출력
- --quality-report: 품질 메트릭 리포트 출력 (v0.7.2)
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

from egress_audit.reversible import ReversibleEgress


def cmd_pseudonymize(args) -> int:
    """``nufi-egress pseudonymize`` CLI handler."""
    restore = getattr(args, "restore", False)
    check = getattr(args, "check", False)
    stream = getattr(args, "stream", False)
    session_id = getattr(args, "session", None)
    text: Optional[str] = getattr(args, "text", None)
    file_path: Optional[str] = getattr(args, "file", None)
    output_path: Optional[str] = getattr(args, "output", None)
    use_json = getattr(args, "json", False)
    fmt = getattr(args, "format", None)
    if fmt == "json":
        use_json = True
    quality_report = getattr(args, "quality_report", False)

    # --check mode: check files for PII, fail if found + suggest pseudonymization
    if check:
        filenames = getattr(args, "filenames", [])
        return _do_check(filenames)

    if stream:
        return _do_stream(session_id, use_json)
    if restore:
        return _do_restore(text, file_path, output_path, session_id, use_json)
    return _do_pseudonymize(text, file_path, output_path, session_id, use_json,
                            quality_report=quality_report)


def _do_stream(
    session_id: Optional[str],
    use_json: bool,
) -> int:
    """스트리밍 모드: stdin 에서 줄 단위로 읽고 가명화 후 즉시 출력.

    LLM SSE/chunked 응답을 파이프로 받아 실시간 가명화하는 용도.
    세션 ID 필수 (이미 가명화된 텍스트의 스트리밍 원복).
    """
    if not session_id:
        print("오류: --stream 모드에서 --session 을 지정해야 합니다.", file=sys.stderr)
        return 1

    rev = ReversibleEgress(ner_backend="gazetteer")
    restorer = rev.stream_restorer(session_id)

    try:
        for line in sys.stdin:
            out = restorer.feed(line)
            if out:
                if use_json:
                    print(json.dumps({"chunk": out}, ensure_ascii=False), flush=True)
                else:
                    sys.stdout.write(out)
                    sys.stdout.flush()
    except KeyboardInterrupt:
        pass

    tail = restorer.flush()
    if tail:
        if use_json:
            print(json.dumps({"chunk": tail}, ensure_ascii=False), flush=True)
        else:
            sys.stdout.write(tail)
            sys.stdout.flush()

    if use_json:
        print(json.dumps({"stats": restorer.stats}, ensure_ascii=False))
    else:
        print(f"\n[stream] stats: {restorer.stats}", file=sys.stderr)

    return 0


def _do_pseudonymize(
    text: Optional[str],
    file_path: Optional[str],
    output_path: Optional[str],
    session_id: Optional[str],
    use_json: bool,
    *,
    quality_report: bool = False,
) -> int:
    if not text and not file_path:
        print("오류: 텍스트 인자 또는 --file 을 지정해야 합니다.", file=sys.stderr)
        return 1

    rev = ReversibleEgress(ner_backend="gazetteer")
    sid = session_id or f"cli-{uuid.uuid4().hex[:12]}"

    if text:
        t0 = time.perf_counter()
        result = rev.pseudonymize(text, sid)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if result.blocked:
            return _output_blocked(text, result, sid, use_json)
        report = None
        if quality_report:
            report = _build_quality_report(
                rev, result, sid, elapsed_ms,
            )
        return _output_pseudonymized(result.transformed_text, sid,
                                     result.pseudonymized, use_json, output_path,
                                     report=report)

    # File mode
    p = Path(file_path)  # type: ignore[arg-type]
    if not p.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {file_path}", file=sys.stderr)
        return 1

    content = p.read_text(encoding="utf-8")
    t0 = time.perf_counter()
    result = rev.pseudonymize(content, sid)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if result.blocked:
        return _output_blocked(content, result, sid, use_json)
    report = None
    if quality_report:
        report = _build_quality_report(
            rev, result, sid, elapsed_ms,
        )
    return _output_pseudonymized(result.transformed_text, sid,
                                 result.pseudonymized, use_json, output_path,
                                 report=report)


def _do_check(filenames: list) -> int:
    """Check files for PII; exit 1 if found, with pseudonymization suggestions."""
    from enforcement.scan_cmd import _is_binary, _scan_file, ScanResult
    from egress_audit.pipeline import DetectionPipeline

    if not filenames:
        return 0

    pipeline = DetectionPipeline()
    result = ScanResult()
    rev = ReversibleEgress(ner_backend="gazetteer")
    sid = f"check-{uuid.uuid4().hex[:12]}"
    found_pii = False

    for fname in filenames:
        p = Path(fname)
        if not p.is_file() or _is_binary(p):
            continue
        _scan_file(p, pipeline, None, result, patterns=None)

    pii_findings = [f for f in result.findings if f.finding_type.startswith("PII:")]
    if not pii_findings:
        return 0

    found_pii = True
    pii_files = sorted(set(f.file for f in pii_findings))
    print("PII detected — pseudonymization suggested:", file=sys.stderr)
    for fpath in pii_files:
        file_findings = [f for f in pii_findings if f.file == fpath]
        print(f"\n  {fpath}  ({len(file_findings)} PII findings)", file=sys.stderr)
        for f in file_findings:
            print(f"    L{f.line}: [{f.finding_type}] {f.text}", file=sys.stderr)
        try:
            content = Path(fpath).read_text(encoding="utf-8")
            r = rev.pseudonymize(content, sid)
            if not r.blocked and r.pseudonymized > 0:
                print(f"  → 가명화 제안 (session: {sid}):", file=sys.stderr)
                for line in r.transformed_text.splitlines()[:5]:
                    print(f"      {line}", file=sys.stderr)
                if len(r.transformed_text.splitlines()) > 5:
                    print("      ...", file=sys.stderr)
        except (OSError, UnicodeDecodeError):
            pass

    return 1 if found_pii else 0


def _do_restore(
    text: Optional[str],
    file_path: Optional[str],
    output_path: Optional[str],
    session_id: Optional[str],
    use_json: bool,
) -> int:
    if not session_id:
        print("오류: --restore 시 --session 을 지정해야 합니다.", file=sys.stderr)
        return 1
    if not text and not file_path:
        print("오류: 텍스트 인자 또는 --file 을 지정해야 합니다.", file=sys.stderr)
        return 1

    rev = ReversibleEgress(ner_backend="gazetteer")

    if text:
        restored, stats = rev.deanonymize(text, session_id)
    else:
        p = Path(file_path)  # type: ignore[arg-type]
        if not p.exists():
            print(f"오류: 파일을 찾을 수 없습니다: {file_path}", file=sys.stderr)
            return 1
        content = p.read_text(encoding="utf-8")
        restored, stats = rev.deanonymize(content, session_id)

    if use_json:
        obj = {
            "mode": "restore",
            "session_id": session_id,
            "restored_text": restored,
            "stats": stats,
        }
        out = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        out = restored

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(out + "\n", encoding="utf-8")
        print(f"[restore] 결과 기록: {output_path}", file=sys.stderr)
    else:
        print(out)

    return 0


def _output_blocked(
    original: str,
    result,
    session_id: str,
    use_json: bool,
) -> int:
    if use_json:
        obj = {
            "mode": "pseudonymize",
            "blocked": True,
            "session_id": session_id,
            "transformed_text": result.transformed_text,
            "pseudonymized_count": 0,
        }
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(f"[blocked] 강한 PII/비밀이 감지되어 차단되었습니다.", file=sys.stderr)
        print(result.transformed_text)
    return 0


def _build_quality_report(
    rev: ReversibleEgress,
    result,
    session_id: str,
    elapsed_ms: float,
) -> Dict[str, Any]:
    """Build quality metrics for a pseudonymization result."""
    from egress_audit.surrogate import REVERSIBLE_ENTITIES

    findings = result.findings
    # Count total PII entities detected (reversible types only)
    total_entities = len([f for f in findings if f.entity_type in REVERSIBLE_ENTITIES])
    pseudonymized = result.pseudonymized

    coverage = (pseudonymized / total_entities) if total_entities > 0 else 1.0

    # Per-type statistics
    by_type: Dict[str, Dict[str, int]] = {}
    type_counts: Dict[str, int] = defaultdict(int)
    for f in findings:
        if f.entity_type in REVERSIBLE_ENTITIES:
            type_counts[f.entity_type] += 1
    for etype, cnt in type_counts.items():
        by_type[etype] = {"count": cnt, "success": cnt}

    # Reversal accuracy: pseudonymize → deanonymize roundtrip check
    reversal_accuracy = 1.0
    if pseudonymized > 0:
        restored, _stats = rev.deanonymize(result.transformed_text, session_id)
        # Compare restored against original findings
        matched = 0
        for f in findings:
            if f.entity_type in REVERSIBLE_ENTITIES:
                if f.text in restored:
                    matched += 1
                else:
                    # Mark failure in by_type
                    if f.entity_type in by_type:
                        by_type[f.entity_type]["success"] = max(
                            0, by_type[f.entity_type]["success"] - 1
                        )
        reversal_accuracy = (matched / pseudonymized) if pseudonymized > 0 else 1.0

    return {
        "total_entities": total_entities,
        "pseudonymized": pseudonymized,
        "coverage": round(coverage, 4),
        "reversal_accuracy": round(reversal_accuracy, 4),
        "by_type": dict(by_type),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def _render_quality_text(report: Dict[str, Any]) -> str:
    """Render quality report as human-readable text table."""
    lines = [
        "",
        "── 품질 메트릭 리포트 ──────────────────────────",
        f"  총 엔티티 수        : {report['total_entities']}",
        f"  가명화 수           : {report['pseudonymized']}",
        f"  엔티티 커버리지     : {report['coverage']:.1%}",
        f"  역변환 정확도       : {report['reversal_accuracy']:.1%}",
        f"  처리 시간           : {report['elapsed_ms']:.1f} ms",
    ]
    if report["by_type"]:
        lines.append("  타입별 통계:")
        for etype, stats in sorted(report["by_type"].items()):
            lines.append(
                f"    {etype:20s}  건수={stats['count']}  성공={stats['success']}"
            )
    lines.append("────────────────────────────────────────────────")
    return "\n".join(lines)


def _output_pseudonymized(
    transformed: str,
    session_id: str,
    count: int,
    use_json: bool,
    output_path: Optional[str],
    *,
    report: Optional[Dict[str, Any]] = None,
) -> int:
    if use_json:
        obj: Dict[str, Any] = {
            "mode": "pseudonymize",
            "blocked": False,
            "session_id": session_id,
            "transformed_text": transformed,
            "pseudonymized_count": count,
        }
        if report is not None:
            obj["quality_report"] = report
        out = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        out = transformed
        # Print session ID to stderr so it doesn't mix with transformed text
        print(f"[session: {session_id}]", file=sys.stderr)
        if report is not None:
            print(_render_quality_text(report), file=sys.stderr)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            (transformed if not use_json else out) + "\n", encoding="utf-8"
        )
        print(f"[pseudonymize] 결과 기록: {output_path}", file=sys.stderr)
    else:
        print(out)

    return 0
