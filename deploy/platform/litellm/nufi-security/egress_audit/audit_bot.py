"""비동기 감사 봇 (CMP-88 P2) — producer/consumer.

dump/메시지 파일을 읽어 문제를 찾는 봇. 사용자 경로는 producer(게이트웨이·flow tap)
가 파일에 append 만 하므로 **무지연**(NFR2), 봇은 파일 큐를 tail 하며 **준실시간**
(NFR5, enqueue→finding p95 ≤ 5s) 탐지한다.

차등 프로파일(SPEC_CMP85.md §P2 / config/audit_profiles.yaml `detection`):
- **private(경량)**: secrets + strong_pii 만, sampling_rate 적용.
- **public(풀)**: strong·weak PII + secrets + 기밀 키워드 + **flow tap 우회 상관**.

flow tap 우회(게이트웨이 출처가 아닌 public-LLM 행 연결)는 **high-severity**
finding/alert 로 승격한다(SPEC §P1·P2). 본문은 못 읽어도 "누가 우회했나"는 탐지.

모드:
- run_once()      : 큐를 한 번 비우고 종료(테스트·--simulate·배치).
- run_forever()   : 워처 폴 루프 + 워커 N(데몬, 준실시간).
무손실·무중복은 egress_audit.file_queue.FileQueue 가 보장(NFR6).
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .file_queue import Envelope, FileQueue, SourceSpec
from .pipeline import DetectionPipeline, Finding
from .policy import PolicyEngine
from . import pseudonymize as ps

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROFILES = _ROOT / "config" / "audit_profiles.yaml"

# 엔티티 → 탐지기 카테고리(프로파일 detectors 와 매칭).
_SECRET_TYPES = {
    "AWS_ACCESS_KEY", "AWS_SECRET_KEY", "GOOGLE_API_KEY", "SLACK_TOKEN",
    "GITHUB_TOKEN", "OPENAI_KEY", "ANTHROPIC_KEY", "PRIVATE_KEY_BLOCK",
    "JWT", "GENERIC_SECRET", "SECRET",
}
_STRONG_PII_TYPES = {
    "KR_RRN", "KR_FOREIGNER_REG", "KR_PASSPORT", "KR_DRIVER_LICENSE",
    "CREDIT_CARD", "KR_ACCOUNT",
}
_WEAK_PII_TYPES = {"KR_BRN", "KR_PHONE", "EMAIL", "KR_PERSON", "KR_LOCATION"}

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_ALERT_MIN_RANK = _SEVERITY_RANK["high"]   # high·critical → alert


def _category(entity_type: str) -> str:
    if entity_type in _SECRET_TYPES:
        return "secrets"
    if entity_type in _STRONG_PII_TYPES:
        return "strong_pii"
    if entity_type in _WEAK_PII_TYPES:
        return "weak_pii"
    return "weak_pii"  # 미분류는 보수적으로 약 PII 취급


def _text_of(body: Any) -> str:
    """메시지 레코드 body 에서 감사 대상 평문을 추출한다."""
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        if isinstance(body.get("text"), str):
            return body["text"]
        msgs = body.get("messages")
        if isinstance(msgs, list):
            parts: List[str] = []
            for m in msgs:
                c = (m or {}).get("content", "")
                if isinstance(c, list):
                    parts.extend(b.get("text", "") for b in c if isinstance(b, dict))
                else:
                    parts.append(str(c))
            return "\n".join(parts)
        # 응답/에러 등 임의 dict → 직렬화 본문 감사(키워드 탐지용).
        return json.dumps(body, ensure_ascii=False)
    return str(body)


class AuditBot:
    def __init__(self, profiles_path: Optional[str] = None,
                 ner_backend: str = "gazetteer"):
        self.profiles_path = Path(profiles_path
                                  or os.environ.get("EGRESS_AUDIT_PROFILES",
                                                    str(_DEFAULT_PROFILES)))
        cfg = self._load(self.profiles_path)
        self.detection_cfg: Dict[str, Any] = cfg.get("detection", {})
        self.bot_cfg: Dict[str, Any] = cfg.get("audit_bot", {})
        ms_cfg = cfg.get("message_store", {})
        self.confidential_keywords: List[str] = [
            str(k) for k in cfg.get("confidential_keywords", [])]

        # 경로(설정 외부화, NFR3). base_dir 가 상대면 repo 루트 기준.
        def _abs(rel: str) -> Path:
            p = Path(rel)
            return p if p.is_absolute() else (_ROOT / p)

        self.messages_dir = _abs(ms_cfg.get("base_dir", "logs/messages"))
        self.flow_dir = _abs(self.bot_cfg.get("flow_dir", "logs/packets/public"))
        self.findings_path = _abs(self.bot_cfg.get("findings_path",
                                                   "logs/audit_findings.jsonl"))
        self.alerts_path = _abs(self.bot_cfg.get("alerts_path", "logs/alerts.jsonl"))
        self.state_path = _abs(self.bot_cfg.get("state_path",
                                                "logs/audit_state/offsets.json"))
        self.poll_interval = float(self.bot_cfg.get("poll_interval_sec", 0.25))
        self.workers = int(self.bot_cfg.get("workers", 4))
        self.gateway_identity = self.bot_cfg.get("gateway_identity", {}) or {}

        # 탐지 파이프라인(온프렘 gazetteer, 외부 호출 0 — NFR1).
        self.pipeline = DetectionPipeline(enable_ner=True, ner_backend=ner_backend)
        self.policy = PolicyEngine()

        self.queue = FileQueue(self._sources(), self.state_path, _ROOT)
        self._io_lock = threading.Lock()
        self._seen: set[str] = set()
        self._rebuild_seen()

    @staticmethod
    def _load(path: Path) -> Dict[str, Any]:
        if not Path(path).exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _sources(self) -> List[SourceSpec]:
        return [
            SourceSpec("messages_private", self.messages_dir / "private",
                       kind="message", egress_class="private"),
            SourceSpec("messages_public", self.messages_dir / "public",
                       kind="message", egress_class="public"),
            SourceSpec("flow", self.flow_dir, kind="flow", egress_class="public",
                       glob="flow-*.jsonl"),
        ]

    # ---- 무중복: 기존 finding 의 source_id 로 seen 복원 -------------------
    def _rebuild_seen(self) -> None:
        if not self.findings_path.exists():
            return
        with open(self.findings_path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    sid = json.loads(ln).get("source_id")
                except json.JSONDecodeError:
                    continue
                if sid:
                    self._seen.add(sid)

    # ---- 프로파일 ---------------------------------------------------------
    def profile(self, egress_class: str) -> Dict[str, Any]:
        return self.detection_cfg.get(egress_class, {})

    def _sampled_in(self, egress_class: str, source_id: str) -> bool:
        rate = float(self.profile(egress_class).get("sampling_rate", 1.0))
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        # 결정적 샘플링(재현 가능): source_id 해시 기준.
        return (zlib.crc32(source_id.encode("utf-8")) % 10_000) < int(rate * 10_000)

    # ---- 우회 판정 --------------------------------------------------------
    def _is_bypass(self, rec: Dict[str, Any]) -> bool:
        """flow tap 레코드가 게이트웨이 우회인지 판정(src≠게이트웨이).

        P1(capture/flow_tap.py)이 이미 권위 있는 ``bypass``/``via_gateway`` 를
        기록하므로 그것을 우선 신뢰한다. 두 필드가 모두 없을 때만(외부 입력 등)
        gateway_identity 휴리스틱으로 보강한다.
        """
        if "bypass" in rec:
            return bool(rec["bypass"])
        if "via_gateway" in rec:
            return not bool(rec["via_gateway"])
        ids = self.gateway_identity
        hosts = {str(h) for h in ids.get("hosts", [])}
        ips = {str(i) for i in ids.get("ips", [])}
        procs = {str(p) for p in (ids.get("process_names")
                                  or ([ids["process"]] if ids.get("process") else []))}
        src_host = str(rec.get("src_host", ""))
        src_ip = str(rec.get("src_ip", ""))
        # P1 레코드는 출처 프로세스를 'process'(+'pid')로 적는다.
        src_proc = str(rec.get("process") or rec.get("src_process") or "")
        if procs and src_proc:
            return src_proc not in procs
        return not (src_host in hosts or src_ip in ips or src_proc in procs)

    # ---- 한 건 감사 → finding(없으면 None) -------------------------------
    def audit_envelope(self, env: Envelope) -> Optional[Dict[str, Any]]:
        rec = env.record
        if env.kind == "flow":
            return self._audit_flow(rec)
        return self._audit_message(env.egress_class or rec.get("egress_class"), rec)

    def _audit_message(self, egress_class: Optional[str],
                       rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if egress_class not in ("private", "public"):
            return None
        source_id = rec.get("id") or rec.get("conversation_id")
        if not source_id or not self._sampled_in(egress_class, str(source_id)):
            return None
        prof = self.profile(egress_class)
        detset = set(prof.get("detectors", []))
        text = _text_of(rec.get("body"))

        spans: List[Dict[str, Any]] = []
        hit_categories: set[str] = set()
        max_rank = -1

        # PII/비밀 파이프라인 → 프로파일 detectors 로 필터.
        for f in self.pipeline.analyze(text):
            cat = _category(f.entity_type)
            if cat not in detset:
                continue
            sev = self.policy.severity_for(f.entity_type)
            max_rank = max(max_rank, _SEVERITY_RANK.get(sev, 1))
            hit_categories.add(cat)
            spans.append({
                "entity_type": f.entity_type, "category": cat,
                "span": [f.start, f.end], "mask": ps.redact(f.entity_type),
                "severity": sev, "source": f.source,
            })

        # 기밀 키워드(공개 프로파일 등에서만).
        if "confidential_keywords" in detset:
            for kw in self.confidential_keywords:
                idx = text.find(kw)
                if idx >= 0:
                    hit_categories.add("confidential_keywords")
                    max_rank = max(max_rank, _SEVERITY_RANK["high"])
                    spans.append({
                        "entity_type": "CONFIDENTIAL_KEYWORD",
                        "category": "confidential_keywords",
                        "span": [idx, idx + len(kw)], "mask": "[기밀]",
                        "severity": "high", "source": "keyword",
                    })

        if not spans:
            return None
        severity = self._rank_to_sev(max_rank)
        # severity_threshold 미만이면 finding 미생성(private=high 등).
        thr = _SEVERITY_RANK.get(prof.get("severity_threshold", "low"), 0)
        if _SEVERITY_RANK[severity] < thr:
            return None
        return self._finding(
            kind="message", egress_class=egress_class, profile=egress_class,
            severity=severity, detectors=sorted(hit_categories), spans=spans,
            source_id=str(source_id), enqueue_ms=int(rec.get("epoch_ms", 0)),
            extra={"conversation_id": rec.get("conversation_id")})

    def _audit_flow(self, rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # 우회 상관은 public 풀 프로파일에서만 활성.
        if "bypass_correlation" not in set(self.profile("public").get("detectors", [])):
            return None
        if not self._is_bypass(rec):
            return None  # 정상(게이트웨이 출처) 행은 finding 아님.
        flow_id = rec.get("flow_id") or rec.get("id") or str(uuid.uuid4())
        spans = [{
            "entity_type": "GATEWAY_BYPASS", "category": "bypass_correlation",
            "src": rec.get("src_host") or rec.get("src_ip"),
            "src_process": rec.get("process") or rec.get("src_process"),
            "src_pid": rec.get("pid"),
            "dst": rec.get("dst_host") or rec.get("dst_ip"),
            "dst_port": rec.get("dst_port"), "sni": rec.get("sni"),
            "severity": "high", "source": "flow_tap",
        }]
        return self._finding(
            kind="flow_bypass", egress_class="public", profile="public",
            severity="high", detectors=["bypass_correlation"], spans=spans,
            source_id=f"flow:{flow_id}", enqueue_ms=int(rec.get("epoch_ms", 0)),
            extra={"flow_id": flow_id})

    @staticmethod
    def _rank_to_sev(rank: int) -> str:
        for name, r in _SEVERITY_RANK.items():
            if r == rank:
                return name
        return "medium"

    def _finding(self, *, kind: str, egress_class: str, profile: str, severity: str,
                 detectors: List[str], spans: List[dict], source_id: str,
                 enqueue_ms: int, extra: dict) -> Dict[str, Any]:
        now_ms = int(time.time() * 1000)
        latency_ms = max(0, now_ms - enqueue_ms) if enqueue_ms else 0
        finding = {
            "finding_id": str(uuid.uuid4()),
            "kind": kind,
            "egress_class": egress_class,
            "profile": profile,
            "severity": severity,
            "detectors": detectors,
            "spans": spans,                 # 마스킹본만(원문 미보존 → 재유출 방지)
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "enqueue_epoch_ms": enqueue_ms,
            "finding_epoch_ms": now_ms,
            "latency_ms": latency_ms,
            "source_id": source_id,
        }
        finding.update({k: v for k, v in extra.items() if v is not None})
        return finding

    # ---- 출력(내구성 있는 append) ----------------------------------------
    def _emit(self, findings: List[Dict[str, Any]]) -> None:
        if not findings:
            return
        with self._io_lock:
            self.findings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.findings_path, "a", encoding="utf-8") as f:
                for fd in findings:
                    f.write(json.dumps(fd, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            alerts = [fd for fd in findings
                      if _SEVERITY_RANK.get(fd["severity"], 0) >= _ALERT_MIN_RANK]
            if alerts:
                self.alerts_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.alerts_path, "a", encoding="utf-8") as f:
                    for fd in alerts:
                        f.write(json.dumps(fd, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                for fd in alerts:
                    self._notify(fd)            # webhook/메일 훅 자리

    def _notify(self, finding: Dict[str, Any]) -> None:
        """high-severity 알림 훅(운영 시 webhook/메일 연결 자리). PoC=무동작."""
        return

    # ---- 큐 드레인(1회) ---------------------------------------------------
    def run_once(self) -> int:
        """큐의 새 레코드를 한 번 처리하고 emit→commit. 생성 finding 수 반환."""
        envs = self.queue.poll()
        if not envs:
            return 0
        fresh = [e for e in envs if self._dedup_key(e) not in self._seen]
        findings: List[Dict[str, Any]] = []
        if fresh:
            with ThreadPoolExecutor(max_workers=max(1, self.workers)) as ex:
                for fd in ex.map(self.audit_envelope, fresh):
                    if fd is not None:
                        findings.append(fd)
        # emit(내구) → 그 다음 오프셋 커밋(무손실: finding 이 먼저 디스크에).
        self._emit(findings)
        for fd in findings:
            self._seen.add(fd["source_id"])
        # finding 을 낸 적 없는 레코드도 처리 완료로 표시(중복 방지·재처리 차단).
        for e in fresh:
            self._seen.add(self._dedup_key(e))
        self.queue.commit(FileQueue.max_offsets(envs))
        return len(findings)

    @staticmethod
    def _dedup_key(env: Envelope) -> str:
        rec = env.record
        if env.kind == "flow":
            return f"flow:{rec.get('flow_id') or rec.get('id')}"
        return str(rec.get("id") or rec.get("conversation_id"))

    # ---- 데몬(준실시간) ---------------------------------------------------
    def run_forever(self, stop_event: Optional[threading.Event] = None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # 봇 죽어도 사용자 경로 무영향(NFR2)
                print(f"[audit_bot] poll error: {exc}")
            stop.wait(self.poll_interval)


# ---- 준실시간 지표(NFR5 검증용 로컬 스크립트) ----------------------------
def p95_latency_ms(findings_path: Path) -> Optional[float]:
    lat: List[int] = []
    p = Path(findings_path)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                v = json.loads(ln).get("latency_ms")
            except json.JSONDecodeError:
                continue
            if isinstance(v, (int, float)):
                lat.append(int(v))
    if not lat:
        return None
    lat.sort()
    idx = max(0, int(round(0.95 * (len(lat) - 1))))
    return float(lat[idx])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NuFi 비동기 감사 봇")
    ap.add_argument("--profiles", default=None, help="audit_profiles.yaml 경로")
    ap.add_argument("--once", action="store_true", help="큐 1회 드레인 후 종료(배치)")
    ap.add_argument("--simulate", action="store_true",
                    help="--once 와 동일(에어갭/CI: 미리 쌓인 dump 리플레이)")
    ap.add_argument("--daemon", action="store_true", help="폴 루프 데몬(준실시간)")
    ap.add_argument("--report", action="store_true", help="findings p95 지연 출력")
    ap.add_argument("--ner-backend", default="gazetteer")
    args = ap.parse_args(argv)

    bot = AuditBot(profiles_path=args.profiles, ner_backend=args.ner_backend)

    if args.report:
        p95 = p95_latency_ms(bot.findings_path)
        print(f"enqueue→finding p95 = {p95} ms "
              f"({'PASS' if (p95 is not None and p95 <= 5000) else 'n/a/FAIL'} vs NFR5 5000ms)")
        return 0
    if args.daemon:
        print(f"[audit_bot] 데몬 시작 poll={bot.poll_interval}s workers={bot.workers}")
        bot.run_forever()
        return 0
    # 기본: 1회 드레인(--once/--simulate).
    n = bot.run_once()
    print(f"[audit_bot] {n} finding 생성 → {bot.findings_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
