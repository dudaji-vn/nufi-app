"""CMP-87 (CMP-85 P1) binary 수용 기준 검증 하니스.

기준(SPEC_CMP85.md §P1):
  1. flow tap 이 public LLM 목적지로 가는 연결만 캡처(타 목적지 0건).
  2. 게이트웨이 출구 평문 content dump 가 logs/packets/public/ 에 적재된다.
  3. 게이트웨이를 우회한(src≠게이트웨이) public-LLM 행 연결이 flow 로그에 별도 식별.
  4. --simulate 모드로 root 없이(에어갭/CI) 재현 가능.
  5. 캡처 대상이 config/capture_targets.yaml 로 갱신 가능(NFR3).

실행: python3 tests/test_cmp85_p1.py  (하나라도 FAIL → exit 1)
온프렘/에어갭(NFR1): 외부 호출 0, tcpdump 없이 simulate 만으로 동작.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from capture import ContentDumpWriter, FlowTap  # noqa: E402
from capture.targets import CaptureTargets, derive_targets, build_bpf  # noqa: E402
from egress_audit import MessageStore, AuditLogger  # noqa: E402
from gateway.core import Gateway  # noqa: E402

SAMPLES = ROOT / "samples"
results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {crit}" + (f" — {detail}" if detail else ""))


def _profiles_yaml(public_retain_raw: bool) -> str:
    return (
        "version: 1\n"
        "message_store:\n  base_dir: logs/messages\n  rotation: daily\n"
        "profiles:\n"
        "  private:\n    retain_raw: true\n"
        f"  public:\n    retain_raw: {'true' if public_retain_raw else 'false'}\n"
    )


def req(model, content):
    return {"model": model, "messages": [{"role": "user", "content": content}]}


def test_p1(tmp_path):
    tmp = str(tmp_path)
    print("\n== CMP-87 P1 — 패킷 레이어 캡처 + 우회 flow tap ==")

    # --- 캡처 대상: routing.yaml 에서 파생 ---
    targets = CaptureTargets.load()  # 캐시 없으면 routing.yaml 즉석 파생

    # 기준 4: --simulate 로 root 없이 flow tap 재현.
    pkt_dir = os.path.join(tmp, "packets")
    tap = FlowTap(targets=targets, base_dir=pkt_dir)
    stats = tap.simulate(str(SAMPLES / "flow_replay.jsonl"))
    flows = tap.read_flows()
    check("P1.4 --simulate 로 root 없이(에어갭/CI) flow tap 재현",
          stats["seen"] > 0 and stats["captured"] > 0 and len(flows) == stats["captured"],
          f"seen={stats['seen']} captured={stats['captured']} dropped={stats['dropped']}")

    # 기준 1: flow tap 이 public LLM 목적지만 캡처(타 목적지 0건).
    target_hosts = {t.host for t in targets.targets}
    captured_hosts = {f["dst_host"] for f in flows}
    off_target = [f for f in flows
                  if f["dst_host"] not in target_hosts or f["dst_port"] != 443]
    # 리플레이 입력에는 비대상(github/db/pypi)·비443 항목이 섞여 있어야 의미 있는 검증.
    raw = [l for l in open(SAMPLES / "flow_replay.jsonl", encoding="utf-8") if l.strip()]
    check("P1.1 flow tap 이 public LLM 목적지만 캡처(타 목적지 0)",
          len(off_target) == 0 and captured_hosts.issubset(target_hosts)
          and stats["dropped"] > 0 and len(raw) > stats["captured"],
          f"캡처 호스트={sorted(captured_hosts)}, 비대상 캡처={len(off_target)}건, "
          f"입력 {len(raw)}건 중 {stats['dropped']}건 필터아웃")

    # 기준 3: 게이트웨이 우회(src≠게이트웨이) 연결 별도 식별.
    bypass = [f for f in flows if f["bypass"]]
    gw_flows = [f for f in flows if not f["bypass"]]
    bypass_ok = (
        len(bypass) > 0
        and all(f["severity"] == "high" for f in bypass)
        and all(not f["via_gateway"] for f in bypass)
        and all(f["via_gateway"] and f["severity"] == "info" for f in gw_flows)
    )
    check("P1.3 우회(src≠게이트웨이) public-LLM 연결 별도 식별",
          bool(bypass_ok),
          f"우회 {len(bypass)}건(전부 high+src≠gw={bypass_ok}), 정상 게이트웨이 {len(gw_flows)}건")

    # 기준 2: 게이트웨이 출구 평문 content dump 적재.
    msg_dir = os.path.join(tmp, "messages")
    prof = os.path.join(tmp, "profiles.yaml")
    Path(prof).write_text(_profiles_yaml(public_retain_raw=False), encoding="utf-8")
    dump_dir = os.path.join(tmp, "egress_packets")
    store = MessageStore(base_dir=msg_dir, profiles_path=prof)
    dumper = ContentDumpWriter(base_dir=dump_dir)
    gw = Gateway(audit=AuditLogger(path=os.path.join(tmp, "audit.jsonl")),
                 ner_backend="gazetteer", messages=store, content_dump=dumper)

    os.environ["EGRESS_PRIVATE_DOWN"] = "1"  # public 폴백 강제
    gw.process(req("nufi-default", "이번 분기 일정 알려줘"))               # forwarded
    gw.process(req("nufi-default", "연락처 정리: 010-1234-5678 김민수"))   # transformed(가명화)
    os.environ["EGRESS_PRIVATE_DOWN"] = "0"
    gw.process(req("nufi-default", "내부 회의록 요약"))                    # private → dump 없음

    dumps = dumper.read_all()
    files = list((Path(dump_dir) / "public").glob("dump-*.jsonl"))
    dump_ok = (
        len(dumps) == 2                                       # public 2건만 dump
        and all(d["source"] == "gateway_egress" for d in dumps)
        and all(d["dst_host"] in target_hosts for d in dumps)
        and all("http_request" in d and d["http_request"] for d in dumps)
        and len(files) >= 1
    )
    # 가명화 통과본이 dump 되는지(원문 전화번호 미노출) 확인.
    sani = [d for d in dumps if "010-1234-5678" not in str(d["body"])]
    check("P1.2 게이트웨이 출구 평문 content dump 적재(logs/packets/public/)",
          bool(dump_ok and len(sani) == 2),
          f"dump {len(dumps)}건, 파일 {len(files)}개, 평문직렬화 보유, "
          f"가명화통과본={len(sani)==2}")

    # 기준 5: capture_targets.yaml 로 대상 갱신 가능(NFR3).
    #   (a) routing.yaml 에서 파생 → 저장, (b) routing 변경 시 대상이 따라 변경.
    out_targets = os.path.join(tmp, "capture_targets.yaml")
    base = derive_targets()
    ct = CaptureTargets(targets=base, path=Path(out_targets))
    ct.save()
    reloaded = CaptureTargets.load(out_targets)
    saved_ok = ({(t.host, t.port) for t in reloaded.targets}
                == {(t.host, t.port) for t in base}) and Path(out_targets).exists()

    # routing 에 새 public 백엔드 추가 → 파생 대상이 늘어나는지(NFR3 갱신성).
    alt_routing = os.path.join(tmp, "routing_alt.yaml")
    cfg = yaml.safe_load(open(ROOT / "config" / "routing.yaml", encoding="utf-8"))
    cfg["backends"]["gemini-pro"] = {
        "provider": "google", "egress_class": "public",
        "api_base": "https://generativelanguage.googleapis.com"}
    yaml.safe_dump(cfg, open(alt_routing, "w", encoding="utf-8"), allow_unicode=True)
    alt = derive_targets(alt_routing)
    alt_hosts = {t.host for t in alt}
    bpf = build_bpf(alt)
    nfr3_ok = (
        saved_ok
        and "generativelanguage.googleapis.com" in alt_hosts
        and len(alt) == len(base) + 1
        and "generativelanguage.googleapis.com" in bpf
    )
    check("P1.5 capture_targets.yaml 로 대상 갱신 가능(NFR3)",
          bool(nfr3_ok),
          f"저장·재로딩 일치={saved_ok}, routing 변경 반영 {len(base)}→{len(alt)} 대상, "
          f"BPF 갱신={('generativelanguage' in bpf)}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_p1(tmp)
    print("\n== 요약 ==")
    passed = sum(1 for _, ok, _ in results if ok)
    for crit, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {crit}")
    print(f"\n{passed}/{len(results)} 기준 PASS")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
