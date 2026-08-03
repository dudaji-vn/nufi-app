"""CMP-86 (CMP-85 P0) binary 수용 기준 검증 하니스.

기준(SPEC_CMP85.md §P0):
  1. private 질의 → logs/messages/private/ 에만, public 질의 → public/ 에만 적재.
  2. 한 대화의 in(요청)·out(응답)이 동일 conversation_id 로 양쪽 저장.
  3. 라우팅 분류(routing.yaml) == 저장 분류(egress_class) 100% 일치(불일치 0).
  4. config/audit_profiles.yaml 의 retain_raw 로 본문 보존 정책 변경 가능(NFR3).

실행: python3 tests/test_cmp85_p0.py  (하나라도 FAIL → exit 1)
온프렘/에어갭(NFR1): gazetteer NER, 외부 호출 0.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import MessageStore, AuditLogger  # noqa: E402
from gateway.core import Gateway  # noqa: E402
from gateway.router import Router  # noqa: E402

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


def make_gateway(tmp, *, msg_dir, profiles_path=None):
    store = MessageStore(base_dir=msg_dir, profiles_path=profiles_path)
    return Gateway(audit=AuditLogger(path=os.path.join(tmp, "audit.jsonl")),
                   ner_backend="gazetteer", messages=store)


def req(model, content, **extra):
    b = {"model": model, "messages": [{"role": "user", "content": content}]}
    b.update(extra)
    return b


def test_p0(tmp_path):
    tmp = str(tmp_path)
    print("\n== CMP-86 P0 — 메시지 스토어 분리 ==")
    msg_dir = os.path.join(tmp, "messages")
    prof = os.path.join(tmp, "profiles.yaml")
    Path(prof).write_text(_profiles_yaml(public_retain_raw=False), encoding="utf-8")

    gw = make_gateway(tmp, msg_dir=msg_dir, profiles_path=prof)
    store = gw.messages
    router = Router()

    # --- private/public 요청 묶음. (model, force_public) ---
    cases = [
        ("nufi-default", False, "내부 매출 보고서 요약해줘"),          # private
        ("nufi-fast", False, "회의록 정리 부탁해"),                    # private
        ("nufi-default", True, "연락처 정리: 010-1234-5678 김민수"),   # public (약 PII→가명화)
        ("nufi-default", True, "이번 분기 일정 알려줘"),               # public benign
    ]
    expected_class = {}  # conversation_id -> 실제 라우팅 결과의 egress_class
    for model, force_public, content in cases:
        os.environ["EGRESS_PRIVATE_DOWN"] = "1" if force_public else "0"
        resp = gw.process(req(model, content))
        # CMP-247: PII 라우팅이 활성이면 실제 결정(resp.route)이 router.resolve()와
        # 다를 수 있으므로, 실제 응답의 egress_class 를 기준으로 비교한다.
        expected_class[resp.conversation_id] = resp.route.egress_class
    os.environ["EGRESS_PRIVATE_DOWN"] = "0"

    priv = store.read_class("private")
    pub = store.read_class("public")

    # 기준 1: 분리 적재 — private 싱크엔 private 만, public 싱크엔 public 만.
    priv_ok = priv and all(r["egress_class"] == "private" for r in priv)
    pub_ok = pub and all(r["egress_class"] == "public" for r in pub)
    check("P0.1 private/public 분리 적재",
          bool(priv_ok and pub_ok),
          f"private 싱크 {len(priv)}건(전부 private={priv_ok}), "
          f"public 싱크 {len(pub)}건(전부 public={pub_ok})")

    # 기준 2: in/out 양쪽이 동일 conversation_id 로 저장(대화별 in 1 + out 1).
    by_conv: dict[str, set] = {}
    for r in priv + pub:
        by_conv.setdefault(r["conversation_id"], set()).add(r["direction"])
    in_out_complete = by_conv and all(d == {"in", "out"} for d in by_conv.values())
    check("P0.2 in·out 동일 conversation_id 양쪽 저장",
          bool(in_out_complete),
          f"{len(by_conv)}개 대화, in+out 완비={in_out_complete}")

    # 기준 3: 라우팅 분류 == 저장 분류 100% 일치.
    mismatch = sum(1 for r in priv + pub
                   if expected_class.get(r["conversation_id"]) != r["egress_class"])
    check("P0.3 라우팅 분류 == 저장 분류 (불일치 0)",
          mismatch == 0, f"불일치 {mismatch}건 / {len(priv)+len(pub)}레코드")

    # 기준 4: retain_raw 정책으로 public 본문 보존 변경 가능.
    #   같은 PII 요청을 retain_raw=false / true 두 프로파일로 적재해 저장 본문 비교.
    pii_text = "연락처 정리: 010-9876-5432 박지훈"
    os.environ["EGRESS_PRIVATE_DOWN"] = "1"

    dir_f = os.path.join(tmp, "msg_false")
    prof_f = os.path.join(tmp, "prof_false.yaml")
    Path(prof_f).write_text(_profiles_yaml(public_retain_raw=False), encoding="utf-8")
    gw_f = make_gateway(tmp, msg_dir=dir_f, profiles_path=prof_f)
    # CMP-247: PII 라우팅을 비활성화하여 PII 텍스트가 public 경로를 타게 함 (retain_raw 정책 검증용)
    gw_f.router.pii_routing.enabled = False
    gw_f.process(req("nufi-default", pii_text))
    in_f = [r for r in gw_f.messages.read_class("public") if r["direction"] == "in"][0]

    dir_t = os.path.join(tmp, "msg_true")
    prof_t = os.path.join(tmp, "prof_true.yaml")
    Path(prof_t).write_text(_profiles_yaml(public_retain_raw=True), encoding="utf-8")
    gw_t = make_gateway(tmp, msg_dir=dir_t, profiles_path=prof_t)
    gw_t.router.pii_routing.enabled = False
    gw_t.process(req("nufi-default", pii_text))
    in_t = [r for r in gw_t.messages.read_class("public") if r["direction"] == "in"][0]
    os.environ["EGRESS_PRIVATE_DOWN"] = "0"

    raw_phone = "010-9876-5432"
    false_blob = json.dumps(in_f["body"], ensure_ascii=False)
    true_blob = json.dumps(in_t["body"], ensure_ascii=False)
    policy_works = (
        in_f["body_retained"] == "sanitized" and raw_phone not in false_blob and
        in_t["body_retained"] == "raw" and raw_phone in true_blob
    )
    check("P0.4 audit_profiles.retain_raw 로 본문 보존 정책 변경 가능(NFR3)",
          bool(policy_works),
          f"retain_raw=false→{in_f['body_retained']}(원문노출={raw_phone in false_blob}) / "
          f"retain_raw=true→{in_t['body_retained']}(원문노출={raw_phone in true_blob})")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_p0(tmp)
    print("\n== 요약 ==")
    passed = sum(1 for _, ok, _ in results if ok)
    for crit, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {crit}")
    print(f"\n{passed}/{len(results)} 기준 PASS")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
