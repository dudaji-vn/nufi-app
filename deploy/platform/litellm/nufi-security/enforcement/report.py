"""규정준수 리포팅 — 기간별 제출용 리포트 산출(CMP-150).

기존 감사 로그·변경 감사·flow tap 을 **규정준수 리포트 산출물**로 묶는다.
**새 측정·새 벤치는 추가하지 않는다** — 기존 산출물을 read-only 로 재사용한다.

재사용(범위 가드):
  - 감사 결정/우회 집계 · 해시체인 무결성 → 인라인 read-only 유틸
    (``panel_decisions`` / ``panel_bypass_timeline``) + :func:`egress_audit.audit.verify_chain_records`.
  - 정책 변경 감사(누가·언제·무엇 + 해시체인) → :class:`enforcement.policy_ops.PolicyChangeAudit`.

산출:
  - ``report compliance`` — 정책 변경 감사(+해시체인 무결성), 차단/가명화 건수, 우회 탐지 요약.

출력 형식: Markdown / HTML / JSON (감사관·구매자 제출용). 모두 의존성 0(표준 라이브러리).

설계 원칙:
  - **무측정**: 입력은 이미 적재된 로그/산출물뿐. 탐지·벤치 재실행 없음.
  - **read-only**: 입력 파일을 'r' 로만 연다. 산출은 호출자(CLI)가 명시 경로로 기록.
  - **결정론**: 같은 입력 → 같은 리포트(판정 포함).
"""
from __future__ import annotations

import html as _html
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(_ROOT) not in sys.path:  # 스크립트 직접 실행 경로 보장
    sys.path.insert(0, str(_ROOT))

import os  # noqa: E402
from egress_audit.audit import verify_chain_records  # noqa: E402

# --------------------------------------------------------------------------- #
# read-only 로더 (구 dashboards.adapter 에서 인라인 — CMP-194 dashboard 제거)
# --------------------------------------------------------------------------- #
_DEFAULT_AUDIT_LOG = _ROOT / "logs" / "egress_audit.jsonl"
_DEFAULT_FLOW_DIR = _ROOT / "logs" / "packets" / "public"


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out: list = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_audit(path: Optional[str] = None) -> list:
    p = Path(path or os.environ.get("EGRESS_AUDIT_LOG", str(_DEFAULT_AUDIT_LOG)))
    return _read_jsonl(p)


def load_flows(flow_dir: Optional[str] = None,
               paths: Optional[Iterable[str]] = None) -> list:
    recs: list = []
    if paths:
        for p in paths:
            recs.extend(_read_jsonl(Path(p)))
        return recs
    d = Path(flow_dir or os.environ.get("EGRESS_FLOW_DIR", str(_DEFAULT_FLOW_DIR)))
    if d.is_file():
        return _read_jsonl(d)
    if d.exists():
        for p in sorted(d.glob("flow-*.jsonl")):
            recs.extend(_read_jsonl(p))
    return recs


def _mask(text: Optional[str]) -> str:
    if text is None:
        return ""
    n = len(str(text))
    return f"\u00ab{n}\uc790\u00bb" if n else ""


def _redact_finding(f: dict, redact: bool) -> dict:
    out = {
        "entity_type": f.get("entity_type") or f.get("category") or f.get("type"),
        "score": f.get("score"),
        "source": f.get("source"),
        "start": f.get("start"),
        "end": f.get("end"),
    }
    out["text"] = _mask(f.get("text")) if redact else f.get("text")
    return out


def panel_decisions(records: list, *, redact: bool = True, **_kw: Any) -> dict:
    rows = []
    for r in records:
        ents = [f.get("entity_type") or f.get("category") or f.get("type")
                for f in r.get("findings", []) if isinstance(f, dict)]
        dec = r.get("decision") or {}
        rows.append({
            "id": r.get("id"), "ts": r.get("ts"), "epoch_ms": r.get("epoch_ms"),
            "outcome": r.get("outcome"), "blocked": dec.get("blocked"),
            "action_counts": dec.get("action_counts") or {},
            "finding_count": dec.get("finding_count", len(r.get("findings", []))),
            "entity_types": sorted(set(e for e in ents if e)),
            "findings": [_redact_finding(f, redact)
                         for f in r.get("findings", []) if isinstance(f, dict)],
        })
    rows.sort(key=lambda x: x.get("epoch_ms") or 0, reverse=True)
    return {"panel": "decisions", "count": len(rows), "rows": rows, "redacted": redact}


def panel_bypass_timeline(flows: list, **_kw: Any) -> dict:
    rows = []
    for fr in flows:
        rows.append({
            "flow_id": fr.get("flow_id"), "ts": fr.get("ts"),
            "epoch_ms": fr.get("epoch_ms"), "severity": fr.get("severity"),
            "bypass": fr.get("bypass"), "dst_host": fr.get("dst_host") or fr.get("sni"),
            "provider": fr.get("provider"), "via_gateway": fr.get("via_gateway"),
        })
    rows.sort(key=lambda x: x.get("epoch_ms") or 0, reverse=True)
    bypass_n = sum(1 for r in rows if r.get("bypass"))
    return {"panel": "bypass_timeline", "count": len(rows), "bypass_count": bypass_n, "rows": rows}


# 점검항목 커버리지(control coverage) — v0.0.9 P0. 컴플라이언스 매핑 리포트.
# 충족유형(정적, 카탈로그) + direct 항목의 자동판정 status.
COV_DIRECT = "direct"
COV_PARTIAL = "partial"
COV_OUT_OF_SCOPE = "out_of_scope"
COV_MET = "met"          # direct 충족(증빙으로 자동판정)
COV_UNMET = "unmet"      # direct 미충족
COV_NA = "n/a"           # partial/out_of_scope — 자동판정 비대상(정적 라벨)

# 프레임워크(규제) 메타 — 한국 규제 증빙 팩. 표시명 + 렌더 순서.
FRAMEWORK_META: Dict[str, str] = {
    "fsec-ai": "금융분야 AI 보안 안내서",
    "net-sep": "망분리 보안대책",
    "pipa":    "개인정보보호법",
    "cia":     "신용정보법",
    "isms-p":  "ISMS-P 인증기준",
}
FRAMEWORK_ORDER = list(FRAMEWORK_META)
_FW_UNKNOWN = "(미분류)"   # framework 미지정 항목(하위호환) 묶음 표기

# 기본 카탈로그 — 패키지 동봉(enforcement/compliance_catalog.yaml).
_DEFAULT_CATALOG = Path(__file__).resolve().parent / "compliance_catalog.yaml"


# --------------------------------------------------------------------------- #
# 입력 로더 (read-only)
# --------------------------------------------------------------------------- #
def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out






# --------------------------------------------------------------------------- #
# 점검항목 커버리지(control coverage) — 카탈로그 + 자동판정 (v0.0.9 P0)
# --------------------------------------------------------------------------- #
def load_catalog(path: Optional[str] = None) -> dict:
    """통제 카탈로그(YAML) 적재. ``path`` 미지정 시 패키지 동봉 기본 카탈로그."""
    import yaml  # PyYAML — 프로젝트 전역 의존성
    p = Path(path) if path else _DEFAULT_CATALOG
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["_source"] = str(p)
    return data


def _get_path(report: dict, dotted: str) -> Any:
    """'decisions.blocked_by_entity' 같은 점표기 경로로 리포트 값을 가져온다."""
    cur: Any = report
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _eval_rule(rule: dict, report: dict) -> tuple[bool, str]:
    """단일 eval 규칙 → (충족여부, 증빙 문자열). 결정론적·read-only."""
    # 복합 규칙: ``all_of:`` 키 형(카탈로그) 또는 ``type: all_of`` 형 모두 허용.
    sub = rule.get("all_of") if "all_of" in rule else (
        rule.get("rules") if rule.get("type") == "all_of" else None)
    if sub is not None:
        parts = [_eval_rule(r, report) for r in sub]
        met = all(ok for ok, _ in parts)
        return met, "; ".join(ev for _, ev in parts)
    rtype = rule.get("type")
    if rtype == "action_count":
        counts = (_get_path(report, "decisions.action_counts") or {})
        actions = rule.get("actions", [])
        total = sum(int(counts.get(a, 0)) for a in actions)
        hit = ", ".join(f"{a}={int(counts.get(a, 0))}" for a in actions)
        return total > int(rule.get("min", 0)), f"action_counts[{hit}]"
    if rtype == "decisions_total":
        n = int(_get_path(report, "decisions.total") or 0)
        return n > int(rule.get("min", 0)), f"decisions.total={n}"
    if rtype == "field_true":
        v = _get_path(report, rule["path"])
        return bool(v), f"{rule['path']}={v}"
    if rtype == "chain_ok":
        chain = _get_path(report, rule["path"]) or {}
        ok = chain.get("ok") is True
        return ok, f"{rule['path']}.ok={chain.get('ok')}"
    if rtype == "nonempty":
        v = _get_path(report, rule["path"]) or {}
        n = len(v)
        return n > 0, f"{rule['path']}#={n}"
    # 알 수 없는 규칙 타입 — 보수적으로 미충족(증빙에 명시).
    return False, f"unknown_rule:{rtype}"


def _evidence_source(item: dict, report: dict) -> Optional[dict]:
    """direct 충족 항목에 증빙 출처(로그 경로, 체인 해시, 레코드 수)를 부여한다.

    증빙 품질 강화 — 어떤 로그에서 어떤 체인으로 판정되었는지 추적 가능.
    """
    rule = item.get("eval") or {}
    # 규칙이 참조하는 데이터 소스(경로) 식별.
    sources: dict = {}
    # 감사 결정 참조 여부.
    needs_decisions = any(k in str(rule) for k in ("action_count", "decisions_total",
                                                    "blocked_by_entity"))
    needs_chain = "chain_ok" in str(rule) or "integrity_ok" in str(rule)
    needs_policy = "policy_change_audit" in str(rule)
    if needs_decisions or needs_chain:
        chain = _get_path(report, "decisions.chain") or {}
        sources["audit_log"] = {
            "records": int(_get_path(report, "decisions.total") or 0),
            "chain_count": chain.get("count"),
            "chain_ok": chain.get("ok"),
        }
    if needs_chain or "integrity_ok" in str(rule):
        pca_chain = _get_path(report, "policy_change_audit.chain") or {}
        sources["change_log"] = {
            "path": _get_path(report, "policy_change_audit.log"),
            "records": int(_get_path(report, "policy_change_audit.total") or 0),
            "chain_ok": pca_chain.get("ok"),
        }
    if needs_policy:
        sources["policy_change_audit"] = {
            "path": _get_path(report, "policy_change_audit.log"),
            "records": int(_get_path(report, "policy_change_audit.total") or 0),
        }
    return sources if sources else None


def evaluate_control(item: dict, report: dict) -> tuple[str, Optional[str]]:
    """카탈로그 항목 1개 → (status, evidence).

    direct 항목은 eval 규칙으로 met/unmet 을 **자동판정**한다. partial/out_of_scope
    는 정적 라벨(status=n/a)이며 자동판정하지 않는다(증빙 없음).
    """
    ctype = item.get("coverage_type")
    if ctype != COV_DIRECT:
        return COV_NA, None
    rule = item.get("eval")
    if not rule:
        return COV_NA, None
    ok, evidence = _eval_rule(rule, report)
    return (COV_MET if ok else COV_UNMET), evidence


def _empty_rollup() -> Dict[str, int]:
    return {COV_DIRECT: 0, COV_PARTIAL: 0, COV_OUT_OF_SCOPE: 0,
            "direct_met": 0, "direct_unmet": 0}


def _tally(rollup: Dict[str, int], ctype: Optional[str], status: str) -> None:
    """롤업 누산기에 한 항목을 더한다(충족유형 + direct status)."""
    if ctype in rollup:
        rollup[ctype] += 1
    if ctype == COV_DIRECT:
        rollup["direct_met" if status == COV_MET else "direct_unmet"] += 1


def build_control_coverage(report: dict, *, catalog_path: Optional[str] = None,
                           frameworks: Optional[Iterable[str]] = None) -> dict:
    """compliance 리포트 모델 + 통제 카탈로그 → 점검항목 커버리지 섹션.

    각 direct 항목은 기존 증빙(decisions/integrity_ok 등)으로 충족 상태가 자동
    산출되고, partial/out_of_scope 는 정적 라벨로 들어간다. 롤업 카운트(직접 N/
    부분 M/범위밖 K, 직접 충족 x/미충족 y)와 **프레임워크(규제)별 소계**
    (``summary.by_framework``)를 함께 제공한다.

    ``frameworks`` 가 주어지면 그 규제 행만 포함하고 롤업도 필터된 집합 기준으로
    낸다(정보성 필터 — 종료코드 무관). None(기본)이면 전체.

    **종료코드 영향 없음** — 이 섹션은 정보성이다(무결성 게이트만 종료코드 결정).
    """
    catalog = load_catalog(catalog_path)
    fw_filter = set(frameworks) if frameworks is not None else None
    items_out: List[dict] = []
    summary = _empty_rollup()
    by_framework: Dict[str, Dict[str, int]] = {}
    for item in catalog.get("controls", []):
        fw = item.get("framework")
        if fw_filter is not None and fw not in fw_filter:
            continue
        ctype = item.get("coverage_type")
        status, evidence = evaluate_control(item, report)
        _tally(summary, ctype, status)
        _tally(by_framework.setdefault(fw or _FW_UNKNOWN, _empty_rollup()),
               ctype, status)
        ev_src = (_evidence_source(item, report)
                  if ctype == COV_DIRECT and status == COV_MET else None)
        items_out.append({
            "id": item.get("id"),
            "framework": fw,
            "maps_to": item.get("maps_to"),
            "source": item.get("source"),
            "requirement": item.get("requirement"),
            "control": item.get("control"),
            "coverage_type": ctype,
            "status": status,
            "evidence": evidence,
            "evidence_source": ev_src,
            "remediation_ref": item.get("remediation_ref"),
        })
    summary["by_framework"] = by_framework
    return {
        "catalog_version": str(catalog.get("version", "?")),
        "catalog_source": catalog.get("_source"),
        "frameworks_filter": sorted(fw_filter) if fw_filter is not None else None,
        "summary": summary,
        "items": items_out,
    }


# --------------------------------------------------------------------------- #
# 규정준수 리포트
# --------------------------------------------------------------------------- #
def build_compliance_report(*,
                            audit_path: Optional[str] = None,
                            change_log_path: Optional[str] = None,
                            flow_dir: Optional[str] = None,
                            flow_paths: Optional[Iterable[str]] = None,
                            customer: Optional[str] = None,
                            title: Optional[str] = None,
                            controls: bool = True,
                            catalog_path: Optional[str] = None,
                            frameworks: Optional[Iterable[str]] = None) -> dict:
    """정책 변경 감사 + 차단/가명화/우회 요약 리포트 모델 구성(전부 read-only 재사용).

    ``controls`` 가 참이면(기본) 점검항목 커버리지(control coverage) 섹션을 더한다
    — 금융보안원 안내서·망분리 평가기준 대비 NuFi 통제 충족 상태를
    **위 증빙에서 자동 산출**. ``catalog_path`` 로 통제 카탈로그를 오버라이드한다.
    커버리지는 정보성이며 종료코드(무결성 게이트)에 영향을 주지 않는다.
    """
    from enforcement.policy_ops import PolicyChangeAudit

    # 1) 정책 변경 감사(누가·언제·무엇) + 변경로그 해시체인 무결성.
    pca = PolicyChangeAudit(path=change_log_path)
    change_chain = pca.verify_chain()
    change_records = pca.read_all()
    by_action = Counter(r.get("action", "unknown") for r in change_records)

    # 2) 감사 결정 집계 — 차단/가명화 건수.
    all_audit = load_audit(audit_path)
    audit_chain = verify_chain_records(all_audit)
    audit_records = all_audit
    dec = panel_decisions(audit_records, redact=True)
    by_outcome: Counter = Counter()
    action_counts: Counter = Counter()
    by_entity: Counter = Counter()
    for row in dec["rows"]:
        by_outcome[row.get("outcome", "unknown")] += 1
        for act, n in (row.get("action_counts") or {}).items():
            action_counts[act] += int(n)
        for et in row.get("entity_types", []):
            by_entity[et] += 1

    # 3) 우회 탐지 요약(flow tap → 어댑터 타임라인 재사용).
    flows = load_flows(flow_dir, flow_paths) if (flow_dir or flow_paths) else []
    bypass = panel_bypass_timeline(flows)

    # 무결성 종합: 두 해시체인이 모두 정상(또는 체인 미부착)이면 ok.
    chains_ok = (audit_chain.get("ok") in (True, None)) and bool(change_chain.get("ok"))

    rep = {
        "kind": "compliance",
        "title": title or "규정준수 리포트",
        "customer": customer,
        "generated_note": "기존 감사 로그·변경 감사·flow tap 재사용 — 새 측정 없음(read-only).",
        "integrity_ok": chains_ok,
        "policy_change_audit": {
            "log": str(pca.path),
            "total": len(change_records),
            "by_action": dict(by_action.most_common()),
            "chain": change_chain,
            "records": change_records,
        },
        "decisions": {
            "total": len(audit_records),
            "by_outcome": dict(by_outcome.most_common()),
            "action_counts": dict(action_counts.most_common()),
            "blocked_by_entity": dict(by_entity.most_common()),
            "chain": audit_chain,
        },
        "bypass": {
            "observed": bypass["count"],
            "bypass_count": bypass["bypass_count"],
            "rows": bypass["rows"],
        },
    }

    # 4) 점검항목 커버리지(control coverage) — 위 증빙에서 자동 산출(정보성).
    if controls:
        rep["control_coverage"] = build_control_coverage(
            rep, catalog_path=catalog_path, frameworks=frameworks)

    return rep


# --------------------------------------------------------------------------- #
# 렌더러 — Markdown / HTML / JSON
# --------------------------------------------------------------------------- #


def _fw_label(fw: str) -> str:
    """프레임워크 id → '표시명 (id)' (미지정은 묶음 라벨)."""
    name = FRAMEWORK_META.get(fw)
    return f"{name} ({fw})" if name else fw


def _ordered_frameworks(d: Dict[str, Any]) -> List[str]:
    """프레임워크 키를 표준 순서(FRAMEWORK_ORDER)로, 미지정은 뒤에 정렬."""
    known = [fw for fw in FRAMEWORK_ORDER if fw in d]
    rest = sorted(k for k in d if k not in FRAMEWORK_ORDER)
    return known + rest


def _group_items_by_framework(items: List[dict]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for it in items:
        out.setdefault(it.get("framework") or _FW_UNKNOWN, []).append(it)
    return out


def _cov_badge(item: dict) -> str:
    """커버리지 항목 → 배지 텍스트(충족유형 + direct status 반영)."""
    ctype = item.get("coverage_type")
    if ctype == COV_DIRECT:
        return "✅ 충족" if item.get("status") == COV_MET else "⚠️ 미충족"
    if ctype == COV_PARTIAL:
        return "🟡 부분충족"
    return "⛔ 범위밖"


def _cov_badge_cls(item: dict) -> str:
    ctype = item.get("coverage_type")
    if ctype == COV_DIRECT:
        return "meet" if item.get("status") == COV_MET else "violation"
    return "nodata"


def render_compliance_md(rep: dict) -> str:
    L: List[str] = []
    L.append(f"# {rep['title']}")
    if rep.get("customer"):
        L.append(f"**고객:** {rep['customer']}  ")
    integ = "✅ 무결성 정상" if rep["integrity_ok"] else "❌ 무결성 위반(변조 의심)"
    L.append(f"**해시체인 무결성:** {integ}")
    L.append("")
    L.append("> " + rep["generated_note"])
    L.append("")

    pa = rep["policy_change_audit"]
    ch = pa["chain"]
    chtxt = "OK" if ch.get("ok") else f"BROKEN — {ch.get('error')} @seq {ch.get('broken_seq')}"
    L.append("## 1. 정책 변경 감사 (누가·언제·무엇)")
    L.append(f"로그: `{pa['log']}`  ·  총 {pa['total']}건  ·  체인: **{chtxt}** ({ch.get('count', 0)}건)")
    L.append("")
    if pa["records"]:
        L.append("| 시각 | 주체 | 동작 | 프로파일 | 버전 | 메모 |")
        L.append("|---|---|---|---|---|---|")
        for r in pa["records"]:
            fv, tv = r.get("from_version"), r.get("to_version")
            ver = (f"v{fv}→v{tv}" if fv is not None else (f"v{tv}" if tv is not None else "—"))
            L.append(f"| {r.get('ts','')} | {r.get('actor','')} | {r.get('action','')} | "
                     f"{r.get('profile','')} | {ver} | {r.get('note','')} |")
    else:
        L.append("_(변경 기록 없음)_")
    L.append("")

    d = rep["decisions"]
    dch = d["chain"]
    dchtxt = ("미부착" if dch.get("ok") is None else
              ("OK" if dch.get("ok") else f"BROKEN @seq {dch.get('broken_seq')}"))
    L.append("## 2. 차단·가명화 집계")
    L.append(f"감사 행 {d['total']}건  ·  감사 해시체인: **{dchtxt}**")
    L.append("")
    L.append("| 항목 | 건수 |")
    L.append("|---|---|")
    for outcome, n in d["by_outcome"].items():
        L.append(f"| outcome:{outcome} | {n} |")
    for act, n in d["action_counts"].items():
        L.append(f"| action:{act} | {n} |")
    L.append("")
    if d["blocked_by_entity"]:
        L.append("**차단 엔티티별:** " + ", ".join(f"{et}={n}" for et, n in d["blocked_by_entity"].items()))
        L.append("")

    b = rep["bypass"]
    L.append("## 3. 우회 탐지 요약")
    L.append(f"관측 flow {b['observed']}건  ·  **우회 {b['bypass_count']}건**")
    if b["bypass_count"]:
        L.append("")
        L.append("| 시각 | 목적지 | 프로세스 | 심각도 |")
        L.append("|---|---|---|---|")
        for r in b["rows"]:
            if not r.get("bypass"):
                continue
            L.append(f"| {r.get('ts','')} | {r.get('dst_host','')} | "
                     f"{r.get('process','')} | {r.get('severity','')} |")
    L.append("")

    cc = rep.get("control_coverage")
    if cc:
        s = cc["summary"]
        L.append("## 4. 점검항목 커버리지 (control coverage)")
        if cc.get("frameworks_filter"):
            L.append(f"_프레임워크 필터: {', '.join(cc['frameworks_filter'])}_  ")
        L.append(f"카탈로그 v{cc['catalog_version']}  ·  "
                 f"**직접 {s['direct']}**(충족 {s['direct_met']}/미충족 {s['direct_unmet']})  ·  "
                 f"**부분 {s['partial']}**  ·  **범위밖 {s['out_of_scope']}**")
        L.append("")
        L.append("> 한국 규제(금융 AI 안내서·망분리·개인정보보호법·신용정보법·ISMS-P) 대비 "
                 "NuFi 통제 충족 — 위 증빙에서 자동 산출(정보성; 종료코드 미반영). "
                 "동일 통제가 여러 규제를 충족(maps_to)함을 규제별 행으로 투명하게 보인다.")
        L.append("")
        # 프레임워크별 소계
        bf = s.get("by_framework", {})
        if bf:
            L.append("### 프레임워크별 소계")
            L.append("| 규제 | 직접(충족/미충족) | 부분 | 범위밖 |")
            L.append("|---|---|---|---|")
            for fw in _ordered_frameworks(bf):
                r = bf[fw]
                L.append(f"| {_fw_label(fw)} | {r['direct']} "
                         f"({r['direct_met']}/{r['direct_unmet']}) | "
                         f"{r['partial']} | {r['out_of_scope']} |")
            L.append("")
        # 프레임워크별 매핑 표(기존 컬럼 유지 + 교차참조)
        items_by_fw = _group_items_by_framework(cc["items"])
        for fw in _ordered_frameworks(items_by_fw):
            r = bf.get(fw, {})
            sub = (f" — 직접 {r['direct']}(충족 {r['direct_met']}/미충족 {r['direct_unmet']})"
                   f"·부분 {r['partial']}·범위밖 {r['out_of_scope']}") if r else ""
            L.append(f"### {_fw_label(fw)}{sub}")
            L.append("| 항목 | 출처 | 요구사항 | NuFi 통제 | 충족 | 증빙/보강 |")
            L.append("|---|---|---|---|---|---|")
            for it in items_by_fw[fw]:
                note = it.get("evidence") or it.get("remediation_ref") or "—"
                mt = f" (←{it['maps_to']})" if it.get("maps_to") else ""
                L.append(f"| {it['id']}{mt} | {it.get('source','')} | "
                         f"{it.get('requirement','')} | {it.get('control','')} | "
                         f"{_cov_badge(it)} | {note} |")
            L.append("")
    return "\n".join(L)


def _html_doc(title: str, body: str) -> str:
    css = (
        "body{font-family:-apple-system,Segoe UI,Roboto,'Noto Sans KR',sans-serif;"
        "max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.55}"
        "h1{border-bottom:2px solid #333;padding-bottom:.3rem}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}"
        "th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.92rem}"
        "th{background:#f2f2f2}"
        ".meet{color:#0a7d2c;font-weight:600}.violation{color:#c0182b;font-weight:600}"
        ".nodata{color:#888}blockquote{color:#555;border-left:4px solid #ddd;margin:0;padding:.2rem 1rem}"
    )
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<title>{_html.escape(title)}</title><style>{css}</style></head>"
            f"<body>{body}</body></html>")


def render_compliance_html(rep: dict) -> str:
    b: List[str] = [f"<h1>{_html.escape(rep['title'])}</h1>"]
    if rep.get("customer"):
        b.append(f"<p><b>고객:</b> {_html.escape(rep['customer'])}</p>")
    integ = ("<span class='meet'>✅ 무결성 정상</span>" if rep["integrity_ok"]
             else "<span class='violation'>❌ 무결성 위반(변조 의심)</span>")
    b.append(f"<p><b>해시체인 무결성:</b> {integ}</p>")
    b.append(f"<blockquote>{_html.escape(rep['generated_note'])}</blockquote>")

    pa = rep["policy_change_audit"]
    ch = pa["chain"]
    chtxt = "OK" if ch.get("ok") else f"BROKEN @seq {ch.get('broken_seq')}"
    b.append("<h2>1. 정책 변경 감사 (누가·언제·무엇)</h2>")
    b.append(f"<p>로그: <code>{_html.escape(pa['log'])}</code> · 총 {pa['total']}건 · 체인: <b>{chtxt}</b></p>")
    if pa["records"]:
        b.append("<table><tr><th>시각</th><th>주체</th><th>동작</th><th>프로파일</th><th>버전</th><th>메모</th></tr>")
        for r in pa["records"]:
            fv, tv = r.get("from_version"), r.get("to_version")
            ver = (f"v{fv}→v{tv}" if fv is not None else (f"v{tv}" if tv is not None else "—"))
            b.append("<tr>" + "".join(f"<td>{_html.escape(str(x))}</td>" for x in
                     [r.get('ts',''), r.get('actor',''), r.get('action',''),
                      r.get('profile',''), ver, r.get('note','')]) + "</tr>")
        b.append("</table>")

    d = rep["decisions"]
    b.append("<h2>2. 차단·가명화 집계</h2>")
    b.append(f"<p>감사 행 {d['total']}건</p><table><tr><th>항목</th><th>건수</th></tr>")
    for outcome, n in d["by_outcome"].items():
        b.append(f"<tr><td>outcome:{_html.escape(outcome)}</td><td>{n}</td></tr>")
    for act, n in d["action_counts"].items():
        b.append(f"<tr><td>action:{_html.escape(act)}</td><td>{n}</td></tr>")
    b.append("</table>")

    bp = rep["bypass"]
    b.append("<h2>3. 우회 탐지 요약</h2>")
    b.append(f"<p>관측 flow {bp['observed']}건 · <b>우회 {bp['bypass_count']}건</b></p>")

    cc = rep.get("control_coverage")
    if cc:
        s = cc["summary"]
        b.append("<h2>4. 점검항목 커버리지 (control coverage)</h2>")
        if cc.get("frameworks_filter"):
            b.append(f"<p><i>프레임워크 필터: "
                     f"{_html.escape(', '.join(cc['frameworks_filter']))}</i></p>")
        b.append(f"<p>카탈로그 v{_html.escape(cc['catalog_version'])} · "
                 f"<b>직접 {s['direct']}</b>(충족 {s['direct_met']}/미충족 {s['direct_unmet']}) · "
                 f"<b>부분 {s['partial']}</b> · <b>범위밖 {s['out_of_scope']}</b></p>")
        b.append("<blockquote>한국 규제(금융 AI 안내서·망분리·개인정보보호법·신용정보법·"
                 "ISMS-P) 대비 NuFi 통제 충족 — 위 증빙에서 자동 산출(정보성; 종료코드 "
                 "미반영). 동일 통제가 여러 규제를 충족(maps_to)함을 규제별 행으로 보인다."
                 "</blockquote>")
        bf = s.get("by_framework", {})
        if bf:
            b.append("<h3>프레임워크별 소계</h3>")
            b.append("<table><tr><th>규제</th><th>직접(충족/미충족)</th>"
                     "<th>부분</th><th>범위밖</th></tr>")
            for fw in _ordered_frameworks(bf):
                r = bf[fw]
                b.append(f"<tr><td>{_html.escape(_fw_label(fw))}</td>"
                         f"<td>{r['direct']} ({r['direct_met']}/{r['direct_unmet']})</td>"
                         f"<td>{r['partial']}</td><td>{r['out_of_scope']}</td></tr>")
            b.append("</table>")
        items_by_fw = _group_items_by_framework(cc["items"])
        for fw in _ordered_frameworks(items_by_fw):
            r = bf.get(fw, {})
            sub = (f" — 직접 {r['direct']}(충족 {r['direct_met']}/미충족 {r['direct_unmet']})"
                   f"·부분 {r['partial']}·범위밖 {r['out_of_scope']}") if r else ""
            b.append(f"<h3>{_html.escape(_fw_label(fw) + sub)}</h3>")
            b.append("<table><tr><th>항목</th><th>출처</th><th>요구사항</th>"
                     "<th>NuFi 통제</th><th>충족</th><th>증빙/보강</th></tr>")
            for it in items_by_fw[fw]:
                note = it.get("evidence") or it.get("remediation_ref") or "—"
                badge = f"<span class='{_cov_badge_cls(it)}'>{_html.escape(_cov_badge(it))}</span>"
                idtxt = it["id"] + (f" (←{it['maps_to']})" if it.get("maps_to") else "")
                cells = "".join(f"<td>{_html.escape(str(x))}</td>" for x in
                                [idtxt, it.get("source", ""), it.get("requirement", ""),
                                 it.get("control", "")])
                b.append(f"<tr>{cells}<td>{badge}</td><td>{_html.escape(note)}</td></tr>")
            b.append("</table>")
    return _html_doc(rep["title"], "".join(b))


# --------------------------------------------------------------------------- #
# 통합 렌더 디스패치
# --------------------------------------------------------------------------- #
def render(report: dict, fmt: str = "md") -> str:
    """리포트 모델 → 문자열. fmt ∈ {md, html, json}."""
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    if fmt == "html":
        return render_compliance_html(report)
    return render_compliance_md(report)
