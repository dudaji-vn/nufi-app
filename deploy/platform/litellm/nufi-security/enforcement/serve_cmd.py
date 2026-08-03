"""``nufi-egress serve`` — HTTP API 모드 (patch155/158/159/170/179/CMP-367).

FastAPI 기반 REST API로 NuFi 탐지 기능을 마이크로서비스에 제공한다.

Endpoints:
  POST   /detect        — PII 탐지
  POST   /route         — 라우팅 결정
  POST   /inspect       — 통합 분석
  POST   /mask          — PII 마스킹
  POST   /redact        — PII 리댁션
  POST   /injection     — 프롬프트 인젝션 탐지
  POST   /pipeline      — 전체 파이프라인 실행
  POST   /explain       — 탐지 결과 상세 설명
  POST   /posture       — 보안 자세 스냅샷
  POST   /pseudonymize  — 가역 가명화 (CMP-367)
  POST   /deanonymize   — 가명화 원복 (CMP-367)
  DELETE /sessions/{id} — 세션 종료 (CMP-367)
  GET    /summary       — 요약 대시보드
  GET    /stats         — NuFi 통계
  GET    /health        — 헬스 체크
  GET    /docs          — Swagger UI (auto)
  GET    /redoc         — ReDoc (auto)
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Request/Response models (module-level for FastAPI OpenAPI schema)
# ---------------------------------------------------------------------------

class DetectRequest(BaseModel):
    """Request body for /detect endpoint."""
    text: str = Field(..., description="Text to scan for PII")


class FindingItem(BaseModel):
    """A single PII finding."""
    entity_type: str = Field(..., description="Type of entity detected (e.g. KR_PHONE)")
    text: str = Field(..., description="Matched text")
    start: int = Field(..., description="Start offset")
    end: int = Field(..., description="End offset")


class DetectResponse(BaseModel):
    """Response from /detect endpoint."""
    findings: List[FindingItem] = Field(default_factory=list, description="List of PII findings")
    count: int = Field(0, description="Number of findings")


class RouteRequest(BaseModel):
    """Request body for /route endpoint."""
    text: str = Field(..., description="Text to evaluate for routing")


class RouteResponse(BaseModel):
    """Response from /route endpoint."""
    target_model: str = Field(..., description="Chosen model target")
    reason: str = Field("", description="Reason for routing decision")
    pii_detected: bool = Field(False, description="Whether PII was detected")


class MaskRequest(BaseModel):
    """Request body for /mask endpoint."""
    text: str = Field(..., description="Text to mask PII in")


class MaskResponse(BaseModel):
    """Response from /mask endpoint."""
    result: str = Field(..., description="Text with PII masked")


class InspectRequest(BaseModel):
    """Request body for /inspect endpoint."""
    text: str = Field(..., description="Text to inspect")


class InspectResponse(BaseModel):
    """Response from /inspect endpoint."""
    text: str = Field("", description="Original text")
    findings: List[FindingItem] = Field(default_factory=list)
    route: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Response from /health endpoint."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")


class InjectionRequest(BaseModel):
    """Request body for /injection endpoint."""
    text: str = Field(..., description="Text to check for prompt injection")
    min_severity: Optional[str] = Field("low", description="Minimum severity filter (low/medium/high/critical)")


class InjectionFindingItem(BaseModel):
    """A single injection finding."""
    entity_type: str = Field(..., description="Type: PROMPT_INJECTION")
    text: str = Field(..., description="Matched text")
    start: int = Field(..., description="Start offset")
    end: int = Field(..., description="End offset")
    score: float = Field(..., description="Confidence score")


class InjectionResponse(BaseModel):
    """Response from /injection endpoint."""
    injection_detected: bool = Field(..., description="Whether injection patterns were found")
    findings: List[InjectionFindingItem] = Field(default_factory=list, description="List of injection findings")
    severity: str = Field("none", description="Highest severity level among findings")


class PipelineRequest(BaseModel):
    """Request body for /pipeline endpoint."""
    text: str = Field(..., description="Text to process through pipeline")
    actions: List[str] = Field(
        default_factory=lambda: ["detect", "mask", "route"],
        description="Pipeline actions to execute (detect, mask, redact, pseudonymize, route, block-check)",
    )


class PostureRequest(BaseModel):
    """Request body for /posture endpoint."""
    path: str = Field(".", description="Path to directory to evaluate posture for")
    save: bool = Field(False, description="Whether to save the posture snapshot to history")


class ScanRequest(BaseModel):
    """Request body for /scan endpoint."""
    path: str = Field(..., description="Path to file or directory to scan")
    check_injection: bool = Field(False, description="Whether to check for prompt injection")
    fail_on_pii: bool = Field(False, description="Whether to treat PII as a failure condition")


class ExplainRequest(BaseModel):
    """Request body for /explain endpoint."""
    text: str = Field(..., description="Text to explain detection results for")


class PseudonymizeRequest(BaseModel):
    """Request body for /pseudonymize endpoint."""
    text: str = Field(..., description="Text to pseudonymize")
    session_id: Optional[str] = Field(None, description="Session ID (auto-generated if omitted)")


class PseudonymizeResponse(BaseModel):
    """Response from /pseudonymize endpoint."""
    transformed_text: str = Field(..., description="Text with PII replaced by surrogates")
    session_id: str = Field(..., description="Session ID for later deanonymization")
    pseudonymized_count: int = Field(0, description="Number of PII tokens pseudonymized")
    blocked: bool = Field(False, description="Whether the text was blocked (strong PII)")


class DeanonymizeRequest(BaseModel):
    """Request body for /deanonymize endpoint."""
    text: str = Field(..., description="Text with surrogates to restore")
    session_id: str = Field(..., description="Session ID from pseudonymize call")


class DeanonymizeResponse(BaseModel):
    """Response from /deanonymize endpoint."""
    restored_text: str = Field(..., description="Text with surrogates replaced by originals")
    stats: dict = Field(default_factory=dict, description="Restore stats (restored, fallback)")


class SessionDeleteResponse(BaseModel):
    """Response from DELETE /sessions/{session_id}."""
    session_id: str = Field(..., description="Deleted session ID")
    purged: int = Field(0, description="Number of vault entries purged")


# Keep backward-compatible alias
TextRequest = DetectRequest


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _read_version() -> str:
    vf = _ROOT / "VERSION"
    return vf.read_text().strip() if vf.exists() else "unknown"


_TEST_CONSOLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NuFi API Test Console</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
h1 { color: #1a1a2e; }
textarea { width: 100%; height: 120px; font-size: 1rem; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
.btn-row { margin: 1rem 0; display: flex; gap: 0.5rem; flex-wrap: wrap; }
button { padding: 0.5rem 1rem; font-size: 0.9rem; border: none; border-radius: 4px; background: #4361ee; color: #fff; cursor: pointer; }
button:hover { background: #3a56d4; }
#result { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 1rem; white-space: pre-wrap; font-family: monospace; font-size: 0.85rem; min-height: 100px; }
</style>
</head>
<body>
<h1>NuFi API Test Console</h1>
<textarea id="input" placeholder="Enter text to analyze..."></textarea>
<div class="btn-row">
  <button onclick="callApi('/detect')">Detect</button>
  <button onclick="callApi('/route')">Route</button>
  <button onclick="callApi('/mask')">Mask</button>
  <button onclick="callApi('/redact')">Redact</button>
  <button onclick="callApi('/injection')">Injection Check</button>
</div>
<div id="result">Results will appear here...</div>
<script>
async function callApi(endpoint) {
  const text = document.getElementById('input').value;
  const res = document.getElementById('result');
  res.textContent = 'Loading...';
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text})
    });
    const data = await resp.json();
    res.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    res.textContent = 'Error: ' + e.message;
  }
}
</script>
</body>
</html>
"""


def create_app() -> FastAPI:
    """Create and return the FastAPI application."""
    app = FastAPI(
        title="NuFi API",
        version=_read_version(),
        description="NuFi Egress Security API — PII detection, routing, masking",
    )

    @app.get("/", response_class=HTMLResponse)
    def root():
        return HTMLResponse(content=_TEST_CONSOLE_HTML)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return {"status": "ok", "version": _read_version()}

    @app.post("/detect", response_model=DetectResponse)
    def detect(req: DetectRequest):
        from egress_audit.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        findings = pipeline.analyze(req.text)
        items = [
            {
                "entity_type": f.entity_type,
                "text": f.text,
                "start": f.start,
                "end": f.end,
            }
            for f in findings
        ]
        return {"findings": items, "count": len(items)}

    @app.post("/route", response_model=RouteResponse)
    def route(req: RouteRequest):
        from gateway.pii_router import PiiRouter

        router = PiiRouter()
        decision = router.route(req.text)
        d = decision.to_dict()
        return {
            "target_model": d.get("target_model", ""),
            "reason": d.get("reason", ""),
            "pii_detected": d.get("pii_detected", False),
        }

    @app.post("/inspect", response_model=InspectResponse)
    def inspect(req: InspectRequest):
        from enforcement.inspect_cmd import inspect_text

        return inspect_text(req.text)

    @app.post("/mask", response_model=MaskResponse)
    def mask(req: MaskRequest):
        from enforcement.transform_cmd import _transform_text

        return {"result": _transform_text(req.text, "mask")}

    @app.post("/redact", response_model=MaskResponse)
    def redact(req: MaskRequest):
        from enforcement.transform_cmd import _transform_text

        return {"result": _transform_text(req.text, "redact")}

    @app.post("/injection", response_model=InjectionResponse)
    def injection(req: InjectionRequest):
        from nufi import detect_injection

        min_sev = req.min_severity or "low"
        findings = detect_injection(req.text, min_severity=min_sev)
        items = [
            {
                "entity_type": f.entity_type,
                "text": f.text,
                "start": f.start,
                "end": f.end,
                "score": f.score,
            }
            for f in findings
        ]
        # Determine highest severity
        severity_order = ["low", "medium", "high", "critical"]
        highest = "none"
        for f in findings:
            meta = getattr(f, "match_meta", None) or {}
            sev = meta.get("severity", "low")
            if sev in severity_order:
                if highest == "none" or severity_order.index(sev) > severity_order.index(highest):
                    highest = sev
        return {
            "injection_detected": len(items) > 0,
            "findings": items,
            "severity": highest,
        }

    @app.post("/pipeline")
    def pipeline(req: PipelineRequest):
        from enforcement.pipeline_cmd import run_pipeline

        return run_pipeline(req.text, actions=req.actions)

    @app.post("/explain")
    def explain(req: ExplainRequest):
        from enforcement.explain_cmd import explain_text

        return explain_text(req.text)

    @app.post("/posture")
    def posture(req: PostureRequest):
        """Capture a posture snapshot for the given directory."""
        from enforcement.posture_cmd import capture_posture, save_posture

        target = Path(req.path).resolve()
        snapshot = capture_posture(str(target))
        if req.save:
            save_posture(snapshot)
        return snapshot

    @app.get("/summary")
    def summary():
        """Return summary dashboard data."""
        from enforcement.summary_cmd import collect_summary

        return collect_summary()

    @app.get("/stats")
    def stats():
        """Return NuFi stats data."""
        from enforcement.stats_cmd import collect_stats

        return collect_stats().to_dict()

    @app.post("/scan")
    def scan(req: ScanRequest):
        """Scan a file or directory for PII (and optionally injection patterns).

        Security: only allows scanning paths under the server CWD to prevent
        path traversal attacks.
        """
        import os
        from enforcement.scan_cmd import scan_path

        cwd = Path(os.getcwd()).resolve()
        target = Path(req.path).resolve()

        # Security: prevent path traversal — target must be under CWD
        try:
            target.relative_to(cwd)
        except ValueError:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "Path traversal denied: path must be under server working directory"},
            )

        if not target.exists():
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=404,
                content={"detail": f"Path not found: {req.path}"},
            )

        result = scan_path(str(target), check_injection=req.check_injection)
        data = result.to_dict()

        # Determine risk level
        if data["has_injection"]:
            risk_level = "critical"
        elif data["has_pii"]:
            risk_level = "high" if data["total_findings"] > 5 else "medium"
        else:
            risk_level = "low"

        return {
            "files_scanned": data["files_scanned"],
            "findings": data["findings"],
            "risk_level": risk_level,
            "total_findings": data["total_findings"],
            "failed": req.fail_on_pii and data["has_pii"],
        }

    @app.get("/badge/{badge_type}")
    def badge(badge_type: str):
        """Return an SVG badge image for the given type (grade|recall|injection|tests)."""
        from enforcement.badge_cmd import badge_grade, badge_recall, badge_injection, badge_tests

        generators = {
            "grade": badge_grade,
            "recall": badge_recall,
            "injection": badge_injection,
            "tests": badge_tests,
        }
        gen = generators.get(badge_type)
        if gen is None:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={"detail": f"Unknown badge type: {badge_type}. Valid: grade, recall, injection, tests"},
            )
        svg = gen()
        return Response(content=svg, media_type="image/svg+xml")

    # ------------------------------------------------------------------
    # Pseudonymize / Deanonymize / Session endpoints (CMP-367)
    # ------------------------------------------------------------------

    _reversible_egress = None  # lazy singleton

    def _get_egress():
        nonlocal _reversible_egress
        if _reversible_egress is None:
            from egress_audit.reversible import ReversibleEgress
            _reversible_egress = ReversibleEgress()
        return _reversible_egress

    @app.post("/pseudonymize", response_model=PseudonymizeResponse)
    def pseudonymize(req: PseudonymizeRequest):
        """Pseudonymize PII in text (reversible). Returns a session_id for later restore."""
        egress = _get_egress()
        sid = req.session_id or str(uuid.uuid4())
        result = egress.pseudonymize(req.text, sid)
        return {
            "transformed_text": result.transformed_text,
            "session_id": sid,
            "pseudonymized_count": result.pseudonymized,
            "blocked": result.blocked,
        }

    @app.post("/deanonymize", response_model=DeanonymizeResponse)
    def deanonymize(req: DeanonymizeRequest):
        """Restore pseudonymized surrogates back to originals."""
        egress = _get_egress()
        restored_text, stats = egress.deanonymize(req.text, req.session_id)
        return {"restored_text": restored_text, "stats": stats}

    @app.delete("/sessions/{session_id}", response_model=SessionDeleteResponse)
    def delete_session(session_id: str):
        """End a pseudonymization session and securely purge vault mappings."""
        egress = _get_egress()
        purged = egress.end_session(session_id)
        return {"session_id": session_id, "purged": purged}

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

app = create_app()


def cmd_serve(args) -> int:
    """``nufi-egress serve`` CLI handler — starts uvicorn or exports OpenAPI."""

    # --openapi: dump spec to stdout and exit
    if getattr(args, "openapi", False):
        spec = app.openapi()
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0

    import uvicorn

    host = getattr(args, "host", "localhost")
    port = getattr(args, "port", 8000)
    print(f"NuFi API server running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0
