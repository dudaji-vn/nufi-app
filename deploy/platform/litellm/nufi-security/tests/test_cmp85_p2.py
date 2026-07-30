"""CMP-88 (CMP-85 P2) binary 수용 기준 검증 하니스.

기준(SPEC_CMP85.md §P2):
  1. 봇 미기동/지연 중에도 사용자 요청 경로 지연 증가 없음(인라인 무변/디커플링).
  2. dump 적재 후 finding 생성까지 enqueue→finding p95 ≤ 5s(NFR5).
  3. private/public 레코드에 서로 다른 감사 프로파일 적용(탐지기 집합 상이).
  4. 봇 재시작 시 미처리 레코드만 재개(오프셋 커밋, 유실·중복 0 — NFR6).
  5. flow tap 우회 이벤트가 high-severity finding/alert 로 생성.

실행: python3 tests/test_cmp85_p2.py  (하나라도 FAIL → exit 1)
온프렘/에어갭(NFR1): gazetteer NER, 외부 호출 0.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import AuditBot, MessageStore, p95_latency_ms  # noqa: E402
from egress_audit.file_queue import FileQueue  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {crit}" + (f" — {detail}" if detail else ""))


def _profiles_yaml(tmp: str) -> str:
    """테스트용 audit_profiles.yaml: 경로를 tmp 로 격리, 차등 프로파일 유지."""
    return f"""version: 1
message_store:
  base_dir: {tmp}/messages
  rotation: daily
profiles:
  private:
    retain_raw: true
  public:
    retain_raw: false
detection:
  private:
    detectors: [secrets, strong_pii]
    sampling_rate: 1.0
    severity_threshold: high
  public:
    detectors: [secrets, strong_pii, weak_pii, confidential_keywords, bypass_correlation]
    sampling_rate: 1.0
    severity_threshold: low
confidential_keywords:
  - 대외비
  - 기밀
audit_bot:
  poll_interval_sec: 0.05
  workers: 3
  findings_path: {tmp}/audit_findings.jsonl
  alerts_path: {tmp}/alerts.jsonl
  state_path: {tmp}/audit_state/offsets.json
  flow_dir: {tmp}/packets/public
  gateway_identity:
    hosts: [gateway, localhost]
    ips: [127.0.0.1]
    process: gateway
"""


def _store(tmp, profiles) -> MessageStore:
    return MessageStore(base_dir=f"{tmp}/messages", profiles_path=profiles)


def _write_flow(tmp: str, recs: list[dict]) -> None:
    d = Path(tmp) / "packets" / "public"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "flow-001.jsonl", "a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _findings(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def run(tmp: str):
    prof = os.path.join(tmp, "profiles.yaml")
    Path(prof).write_text(_profiles_yaml(tmp), encoding="utf-8")
    os.environ["EGRESS_AUDIT_PROFILES"] = prof
    store = _store(tmp, prof)

    # --- producer: private/public in·out 메시지 + flow tap 우회 1건 적재 ---
    now = int(time.time() * 1000)
    # public 약 PII(전화/이메일) → 약PII finding(public 프로파일만)
    store.record(conversation_id="c-pub-1", direction="in", egress_class="public",
                 model="gpt-4o", provider="openai",
                 body={"text": "연락처 010-1234-5678 / a@b.com 정리해줘"})
    # public 기밀 키워드
    store.record(conversation_id="c-pub-2", direction="in", egress_class="public",
                 model="gpt-4o", provider="openai",
                 body={"text": "이 문서는 대외비 입니다. 요약."})
    # private 약 PII만(경량 프로파일 → severity_threshold=high 로 finding 미생성)
    store.record(conversation_id="c-prv-1", direction="in", egress_class="private",
                 model="nufi-default", provider="onprem",
                 body={"text": "내부 연락처 010-9999-0000 정리"})
    # private 강 PII(주민번호) → 경량 프로파일도 strong_pii 탐지(high)
    store.record(conversation_id="c-prv-2", direction="in", egress_class="private",
                 model="nufi-default", provider="onprem",
                 body={"text": "주민번호 900101-1234568 확인"})  # 체크섬 통과 RRN

    # flow tap: 게이트웨이 우회 1건(via_gateway=false) + 정상 1건(true)
    _write_flow(tmp, [
        {"flow_id": "f-bypass", "epoch_ms": now, "src_host": "10.0.0.42",
         "src_ip": "10.0.0.42", "src_process": "python", "dst_host": "api.anthropic.com",
         "dst_port": 443, "sni": "api.anthropic.com", "via_gateway": False,
         "egress_class": "public"},
        {"flow_id": "f-ok", "epoch_ms": now, "src_host": "gateway",
         "src_ip": "127.0.0.1", "src_process": "gateway", "dst_host": "api.openai.com",
         "dst_port": 443, "sni": "api.openai.com", "via_gateway": True,
         "egress_class": "public"},
    ])

    # === 기준 1: 디커플링 — 사용자 경로(게이트웨이)는 봇/큐를 import 하지 않는다 ===
    gw_src = (ROOT / "gateway" / "core.py").read_text(encoding="utf-8")
    decoupled = ("audit_bot" not in gw_src and "file_queue" not in gw_src
                 and "FileQueue" not in gw_src and "AuditBot" not in gw_src)
    check("P2.1 사용자 경로 무지연(봇 디커플링: gateway 가 봇/큐 비참조)",
          decoupled, f"gateway/core.py 봇·큐 참조 없음={decoupled}")

    # === 봇 1회 드레인 ===
    bot = AuditBot(profiles_path=prof, ner_backend="gazetteer")
    n = bot.run_once()
    finds = _findings(bot.findings_path)
    by_conv = {f.get("conversation_id"): f for f in finds if f["kind"] == "message"}

    # === 기준 3: private/public 차등 프로파일(탐지기 집합 상이) ===
    pub_phone = by_conv.get("c-pub-1")          # public 약PII → finding 있어야
    prv_phone = by_conv.get("c-prv-1")          # private 약PII → finding 없어야(경량+high임계)
    prv_strong = by_conv.get("c-prv-2")         # private 강PII → finding 있어야
    prof_differ = (
        pub_phone is not None and "weak_pii" in pub_phone["detectors"] and
        prv_phone is None and                                  # 약PII 가 private 에선 누락
        prv_strong is not None and "strong_pii" in prv_strong["detectors"]
        and "weak_pii" not in prv_strong["detectors"]
    )
    check("P2.3 private(경량)/public(풀) 차등 프로파일 적용",
          bool(prof_differ),
          f"public약PII={'O' if pub_phone else 'X'}, private약PII={'O' if prv_phone else 'X(기대)'}, "
          f"private강PII={'O' if prv_strong else 'X'}")

    # === 기준 5: flow tap 우회 → high-severity finding + alert ===
    bypass = [f for f in finds if f["kind"] == "flow_bypass"]
    alerts = _findings(bot.alerts_path)
    alert_ids = {a.get("flow_id") for a in alerts}
    bypass_ok = (
        len(bypass) == 1 and bypass[0].get("flow_id") == "f-bypass"
        and bypass[0]["severity"] == "high"
        and "f-bypass" in alert_ids                  # alert 에도 기록
        and not any(f.get("flow_id") == "f-ok" for f in bypass)  # 정상 행은 finding 아님
    )
    check("P2.5 flow tap 우회 = high-severity finding/alert",
          bool(bypass_ok),
          f"우회 finding={len(bypass)}건, alert에 f-bypass={'O' if 'f-bypass' in alert_ids else 'X'}, "
          f"정상행 제외={'O' if not any(f.get('flow_id')=='f-ok' for f in bypass) else 'X'}")

    # === 기준 2: enqueue→finding p95 ≤ 5s(NFR5) ===
    p95 = p95_latency_ms(bot.findings_path)
    check("P2.2 enqueue→finding p95 ≤ 5s (NFR5)",
          p95 is not None and p95 <= 5000, f"p95={p95} ms (n={len(finds)})")

    # === 기준 4: 재시작 시 미처리분만 재개(오프셋 커밋, 유실·중복 0) ===
    # (a) 재드레인 → 새 레코드 0 이므로 finding 증가 0(중복 0).
    n2 = bot.run_once()
    after_restart_dup = len(_findings(bot.findings_path)) == len(finds) and n2 == 0
    # (b) 새 봇 인스턴스(=재시작): 기존 오프셋 로드 → 기존분 재처리 0.
    bot2 = AuditBot(profiles_path=prof, ner_backend="gazetteer")
    n3 = bot2.run_once()
    no_reprocess = (len(_findings(bot.findings_path)) == len(finds)) and n3 == 0
    # (c) 새 레코드 1건 추가 → 그것만 처리(미처리분만 재개).
    store.record(conversation_id="c-pub-3", direction="in", egress_class="public",
                 model="gpt-4o", provider="openai",
                 body={"text": "추가 연락처 010-2222-3333"})
    bot3 = AuditBot(profiles_path=prof, ner_backend="gazetteer")
    n4 = bot3.run_once()
    only_new = n4 == 1 and any(f.get("conversation_id") == "c-pub-3"
                               for f in _findings(bot.findings_path))
    nfr6_ok = after_restart_dup and no_reprocess and only_new
    check("P2.4 재시작 시 미처리분만 재개(오프셋 커밋, 유실·중복 0 — NFR6)",
          bool(nfr6_ok),
          f"재드레인중복0={after_restart_dup}, 재시작재처리0={no_reprocess}, 신규1건만={only_new}")

    # === 보강: 큐 무손실 — 부분 라인(개행 없는 꼬리)은 소비하지 않는다 ===
    pub_day = Path(tmp) / "messages" / "public"
    pub_file = sorted(pub_day.glob("*.jsonl"))[0]
    with open(pub_file, "a", encoding="utf-8") as f:
        f.write('{"id":"partial","conversation_id":"c-x","direction":"in",'
                '"egress_class":"public","epoch_ms":0,"body":{"text":"미완"}')  # 개행 없음
    bot4 = AuditBot(profiles_path=prof, ner_backend="gazetteer")
    bot4.run_once()
    partial_safe = not any(f.get("conversation_id") == "c-x"
                           for f in _findings(bot.findings_path))
    check("P2.6 (보강) 부분 라인 무손실 — 미완 레코드 미소비",
          partial_safe, f"부분라인 소비안함={partial_safe}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp)
    print("\n== 요약 ==")
    passed = sum(1 for _, ok, _ in results if ok)
    for crit, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {crit}")
    print(f"\n{passed}/{len(results)} 기준 PASS")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
