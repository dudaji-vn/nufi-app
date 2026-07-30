"""PII QA 평가셋 생성기 — LLM 가명화 품질 정량 평가용 한국어 QA 데이터셋.

CMP-350: 가명화해서 LLM에 보내도 응답 품질이 동일한지 정량 증명하기 위한 기준 데이터.

산출물:
  data/pii_qa_eval.jsonl   — 평가셋 (100~200개 샘플)

실행:
  python3 scripts/gen_pii_qa_eval.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import goldset.generate as G  # noqa: E402

SEED = 20260708
OUT = ROOT / "data" / "pii_qa_eval.jsonl"


def _person(rng):
    return rng.choice(G.LISTED_SURNAMES) + rng.choice(G.GIVEN)


def _phone(rng):
    return G.make_phone(rng)


def _email(rng):
    return G.make_email(rng)


def _location(rng):
    return rng.choice(G.GAZ_LOCATIONS + G.NONGAZ_LOCATIONS)


def _brn(rng):
    return G.make_brn(rng)


def _find(text, needle):
    """Find needle in text and return (start, end)."""
    i = text.find(needle)
    assert i >= 0, f"{needle!r} not found in {text!r}"
    return i, i + len(needle)


def _ent(etype, value, start, end):
    return {"type": etype, "value": value, "start": start, "end": end}


def _find_ent(text, etype, value):
    s, e = _find(text, value)
    return _ent(etype, value, s, e)


# ---------------------------------------------------------------------------
# QA 템플릿: (category, question_template, answer_template, pii_specs)
# pii_specs: list of (generator_key, entity_type, placeholder)
# ---------------------------------------------------------------------------

TEMPLATES = [
    # ── customer_service ──
    {
        "cat": "customer_service",
        "q": "고객 {name}님({phone})의 환불 요청을 처리해주세요.",
        "a": "{name}님의 환불 요청을 접수했습니다. {phone}로 처리 결과를 안내드리겠습니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "customer_service",
        "q": "{name} 고객이 {email}로 문의한 배송 지연 건을 확인해주세요.",
        "a": "{name} 고객님의 배송 지연 건을 확인했습니다. {email}로 진행 상황 안내 메일을 발송하겠습니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    {
        "cat": "customer_service",
        "q": "{phone}로 연락 온 고객의 계정 잠금 해제를 요청합니다.",
        "a": "{phone} 고객의 계정 잠금을 해제했습니다. 본인 인증 후 정상 이용 가능합니다.",
        "pii": [("phone", "KR_PHONE")],
    },
    {
        "cat": "customer_service",
        "q": "{name}님이 {location} 매장에서 구매한 제품 교환을 요청했습니다.",
        "a": "{name}님의 제품 교환 요청을 접수했습니다. {location} 매장에서 교환 가능합니다.",
        "pii": [("name", "KR_PERSON"), ("location", "KR_LOCATION")],
    },
    {
        "cat": "customer_service",
        "q": "{name}님({email})이 VIP 등급 혜택에 대해 문의했습니다. 안내해주세요.",
        "a": "{name}님은 현재 VIP 등급으로, 전 상품 10% 할인과 무료배송 혜택이 적용됩니다. 자세한 내용은 {email}로 안내드리겠습니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    # ── document_summary ──
    {
        "cat": "document_summary",
        "q": "다음 계약서를 요약해주세요: 계약 당사자 {name}, 사업자등록번호 {brn}, 계약 금액 5,000만원.",
        "a": "본 계약은 {name}(사업자등록번호: {brn})과 체결된 5,000만원 규모의 계약입니다.",
        "pii": [("name", "KR_PERSON"), ("brn", "KR_BRN")],
    },
    {
        "cat": "document_summary",
        "q": "{name} 대표의 사업자등록번호 {brn}로 등록된 법인 정보를 요약해주세요.",
        "a": "{name} 대표, 사업자등록번호 {brn}로 등록된 법인입니다. 업종 및 매출 현황을 확인했습니다.",
        "pii": [("name", "KR_PERSON"), ("brn", "KR_BRN")],
    },
    {
        "cat": "document_summary",
        "q": "다음 보고서를 요약해주세요: 담당자 {name}, 연락처 {phone}, 프로젝트 진행률 78%.",
        "a": "담당자 {name}({phone})이 관리하는 프로젝트 진행률은 78%입니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "document_summary",
        "q": "{location}에 위치한 지사의 분기별 실적 보고서를 요약해주세요.",
        "a": "{location} 지사의 분기별 실적은 전년 대비 15% 증가했으며, 신규 고객 유치 30건을 달성했습니다.",
        "pii": [("location", "KR_LOCATION")],
    },
    {
        "cat": "document_summary",
        "q": "{name}님이 {email}로 보낸 제안서의 핵심 내용을 정리해주세요.",
        "a": "{name}님이 {email}로 보낸 제안서의 핵심은 AI 기반 자동화 도입으로 운영비 20% 절감입니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    # ── payment ──
    {
        "cat": "payment",
        "q": "{name}님의 {phone}로 등록된 결제 내역을 조회해주세요.",
        "a": "{name}님({phone}) 최근 결제 내역: 2026-07-01 ₩35,000, 2026-07-05 ₩12,800.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "payment",
        "q": "사업자등록번호 {brn}로 세금계산서를 발행해주세요. 담당자 {name}.",
        "a": "사업자등록번호 {brn}로 세금계산서를 발행했습니다. {name} 담당자에게 이메일로 전송합니다.",
        "pii": [("brn", "KR_BRN"), ("name", "KR_PERSON")],
    },
    {
        "cat": "payment",
        "q": "{name}님의 환불금을 {email}로 안내해주세요.",
        "a": "{name}님의 환불금 ₩45,000이 처리되었습니다. {email}로 환불 영수증을 발송했습니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    {
        "cat": "payment",
        "q": "{phone}로 등록된 포인트 잔액을 확인해주세요.",
        "a": "{phone}로 등록된 계정의 포인트 잔액은 15,230포인트입니다.",
        "pii": [("phone", "KR_PHONE")],
    },
    {
        "cat": "payment",
        "q": "{name}님, 사업자등록번호 {brn}에 대한 미납 요금을 확인해주세요.",
        "a": "{name}님(사업자등록번호 {brn}), 미납 요금은 ₩230,000입니다. 7일 이내 납부 부탁드립니다.",
        "pii": [("name", "KR_PERSON"), ("brn", "KR_BRN")],
    },
    # ── hr ──
    {
        "cat": "hr",
        "q": "신규 입사자 {name}({email})의 온보딩 절차를 안내해주세요.",
        "a": "{name}님의 온보딩: 1) {email}로 계정 생성 안내 발송, 2) 보안 교육 수료, 3) 장비 수령.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    {
        "cat": "hr",
        "q": "{name} 사원의 연락처 {phone}를 인사 시스템에 업데이트해주세요.",
        "a": "{name} 사원의 연락처를 {phone}로 업데이트했습니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "hr",
        "q": "{location} 지사로 전보 발령 난 {name}님의 이전 절차를 정리해주세요.",
        "a": "{name}님의 {location} 지사 전보 절차: 1) 인수인계 완료, 2) 좌석 배정, 3) 현지 팀 소개.",
        "pii": [("name", "KR_PERSON"), ("location", "KR_LOCATION")],
    },
    {
        "cat": "hr",
        "q": "{name}님({email})의 휴가 신청 현황을 알려주세요.",
        "a": "{name}님은 올해 연차 15일 중 8일 사용, 잔여 7일입니다. 상세 내역은 {email}로 발송합니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    {
        "cat": "hr",
        "q": "{name} 팀장의 평가 보고서를 작성해주세요. 연락처 {phone}.",
        "a": "{name} 팀장 평가: 리더십 우수, 목표 달성률 95%. 연락처: {phone}.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    # ── medical ──
    {
        "cat": "medical",
        "q": "환자 {name}({phone})의 진료 예약을 변경해주세요.",
        "a": "{name} 환자의 진료 예약을 7월 15일 오후 2시로 변경했습니다. {phone}로 확인 문자를 발송합니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "medical",
        "q": "{name}님의 건강검진 결과를 {email}로 전송해주세요.",
        "a": "{name}님의 건강검진 결과를 {email}로 전송했습니다. 이상 소견은 없습니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    {
        "cat": "medical",
        "q": "{location} 병원에서 {name} 환자의 전원 기록을 조회해주세요.",
        "a": "{name} 환자는 {location} 병원에서 2026-06-20에 전원되었습니다. 현재 상태 안정.",
        "pii": [("name", "KR_PERSON"), ("location", "KR_LOCATION")],
    },
    {
        "cat": "medical",
        "q": "환자 {name}({phone})의 처방전을 확인해주세요.",
        "a": "{name} 환자 처방: 항생제 3일분, 소화제 7일분. {phone}로 복약 안내 발송합니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "medical",
        "q": "{name}님의 보험 청구 서류를 {email}로 보내주세요.",
        "a": "{name}님의 보험 청구 서류를 {email}로 발송했습니다. 처리까지 약 5영업일 소요됩니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    # ── legal ──
    {
        "cat": "legal",
        "q": "{name} 변호사({phone})에게 계약 검토를 요청해주세요.",
        "a": "{name} 변호사에게 계약 검토를 요청했습니다. {phone}로 검토 완료 후 회신 예정입니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE")],
    },
    {
        "cat": "legal",
        "q": "사업자등록번호 {brn}로 등록된 {name}님 관련 소송 이력을 조회해주세요.",
        "a": "{name}님(사업자등록번호 {brn}) 관련 소송 이력: 2025년 민사 1건(종결).",
        "pii": [("name", "KR_PERSON"), ("brn", "KR_BRN")],
    },
    {
        "cat": "legal",
        "q": "{name}님({email})에게 법률 자문 의견서를 전달해주세요.",
        "a": "{name}님에게 법률 자문 의견서를 {email}로 전달했습니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
    {
        "cat": "legal",
        "q": "{location}에서 발생한 사건의 담당 변호사 {name}({phone})에게 연락해주세요.",
        "a": "{location} 사건 담당 {name} 변호사에게 {phone}로 연락했습니다.",
        "pii": [("name", "KR_PERSON"), ("phone", "KR_PHONE"), ("location", "KR_LOCATION")],
    },
    {
        "cat": "legal",
        "q": "{name}님의 상표 등록 진행 상황을 {email}로 알려주세요.",
        "a": "{name}님의 상표 등록은 현재 심사 중입니다. 결과를 {email}로 안내드리겠습니다.",
        "pii": [("name", "KR_PERSON"), ("email", "EMAIL")],
    },
]

# Control group templates (no PII) — 10~20% of total
CONTROL_TEMPLATES = [
    {
        "cat": "customer_service",
        "q": "최근 출시된 신제품의 주요 기능을 설명해주세요.",
        "a": "신제품의 주요 기능은 AI 기반 자동 분류, 실시간 알림, 다국어 지원입니다.",
    },
    {
        "cat": "document_summary",
        "q": "2분기 매출 보고서의 핵심 내용을 요약해주세요.",
        "a": "2분기 매출은 전년 대비 12% 증가했으며, 해외 매출 비중이 35%로 상승했습니다.",
    },
    {
        "cat": "payment",
        "q": "현재 진행 중인 프로모션 할인율을 알려주세요.",
        "a": "현재 여름 시즌 프로모션으로 전 상품 15% 할인이 적용되고 있습니다.",
    },
    {
        "cat": "hr",
        "q": "올해 하반기 채용 계획을 알려주세요.",
        "a": "하반기 채용 계획: 개발 5명, 마케팅 3명, 영업 2명으로 총 10명을 채용할 예정입니다.",
    },
    {
        "cat": "medical",
        "q": "독감 예방접종 일정을 안내해주세요.",
        "a": "독감 예방접종은 10월 1일부터 시작되며, 사전 예약은 9월 15일부터 가능합니다.",
    },
    {
        "cat": "legal",
        "q": "개인정보 처리방침 변경 시 필수 고지 사항을 정리해주세요.",
        "a": "변경 7일 전 고지 필수이며, 수집 목적, 항목, 보유 기간, 제3자 제공 여부를 명시해야 합니다.",
    },
    {
        "cat": "customer_service",
        "q": "반품 절차와 소요 기간을 안내해주세요.",
        "a": "반품은 수령 후 7일 이내 신청 가능하며, 접수 후 3~5영업일 내 환불 처리됩니다.",
    },
    {
        "cat": "document_summary",
        "q": "클라우드 마이그레이션 프로젝트의 리스크 요소를 정리해주세요.",
        "a": "주요 리스크: 1) 데이터 손실 가능성, 2) 다운타임 발생, 3) 비용 초과, 4) 보안 취약점 노출.",
    },
    {
        "cat": "hr",
        "q": "원격 근무 정책의 주요 내용을 설명해주세요.",
        "a": "주 2일 원격 근무 가능, 코어 타임 10시~16시 필수 접속, 월 1회 오피스 데이 참석 필수입니다.",
    },
    {
        "cat": "legal",
        "q": "계약 해지 시 위약금 산정 기준을 설명해주세요.",
        "a": "잔여 계약 기간의 월 이용료 합계의 10%가 위약금으로 산정됩니다.",
    },
    {
        "cat": "payment",
        "q": "정기결제 해지 절차를 안내해주세요.",
        "a": "마이페이지 > 결제관리에서 정기결제를 해지할 수 있으며, 해지 즉시 다음 결제부터 적용됩니다.",
    },
    {
        "cat": "medical",
        "q": "비타민D 권장 섭취량과 부족 시 증상을 알려주세요.",
        "a": "성인 기준 하루 600~800IU이며, 부족 시 피로감, 근육통, 면역력 저하가 나타날 수 있습니다.",
    },
    {
        "cat": "customer_service",
        "q": "온라인 주문 후 매장 수령(픽업) 서비스 이용 방법을 알려주세요.",
        "a": "주문 시 '매장 픽업'을 선택하고, 준비 완료 알림을 받은 후 매장에서 수령하시면 됩니다.",
    },
    {
        "cat": "document_summary",
        "q": "올해 정보보안 감사 결과의 주요 지적사항을 정리해주세요.",
        "a": "주요 지적사항: 1) 접근 권한 주기적 검토 미흡, 2) 로그 보관 기간 미준수, 3) 암호화 정책 미적용 구간 존재.",
    },
    {
        "cat": "hr",
        "q": "퇴직금 중간정산 신청 요건을 설명해주세요.",
        "a": "근속 1년 이상이며 무주택자 주택구입, 본인 또는 부양가족 6개월 이상 요양 등의 사유가 있어야 합니다.",
    },
    {
        "cat": "legal",
        "q": "전자서명의 법적 효력에 대해 설명해주세요.",
        "a": "전자서명법에 따라 공인전자서명은 수기서명과 동일한 법적 효력을 가집니다.",
    },
    {
        "cat": "medical",
        "q": "건강검진 주기와 필수 검사 항목을 알려주세요.",
        "a": "직장인은 2년마다 일반건강검진, 40세 이상은 암검진이 추가됩니다. 필수 항목: 혈액검사, 소변검사, 흉부X-ray.",
    },
    {
        "cat": "payment",
        "q": "해외 결제 시 환율 적용 기준을 설명해주세요.",
        "a": "해외 결제는 카드사 매입일 기준 환율이 적용되며, 국제 브랜드 수수료 1%가 추가됩니다.",
    },
    {
        "cat": "customer_service",
        "q": "제품 보증 기간 연장 서비스에 대해 안내해주세요.",
        "a": "기본 보증 1년에 추가 1년 연장 가능하며, 구매 후 30일 이내에 신청해야 합니다.",
    },
    {
        "cat": "document_summary",
        "q": "최근 개정된 근로기준법의 주요 변경사항을 요약해주세요.",
        "a": "주요 변경: 1) 유연근무 확대, 2) 육아휴직 기간 연장, 3) 퇴직금 산정 기준 변경.",
    },
]


def _gen_pii_value(rng, pii_type):
    if pii_type == "KR_PERSON":
        return _person(rng)
    elif pii_type == "KR_PHONE":
        return _phone(rng)
    elif pii_type == "EMAIL":
        return _email(rng)
    elif pii_type == "KR_LOCATION":
        return _location(rng)
    elif pii_type == "KR_BRN":
        return _brn(rng)
    raise ValueError(f"Unknown PII type: {pii_type}")


def generate_dataset():
    rng = random.Random(SEED)
    rows = []
    idx = 0

    # Generate PII samples — cycle through templates multiple times
    # With 30 templates, ~5 passes gives ~150 PII samples
    num_passes = 5
    for pass_i in range(num_passes):
        for tmpl in TEMPLATES:
            idx += 1
            # Generate PII values
            values = {}
            for placeholder, pii_type in tmpl["pii"]:
                values[placeholder] = _gen_pii_value(rng, pii_type)

            question = tmpl["q"].format(**values)
            answer = tmpl["a"].format(**values)

            # Build pii_entities with correct offsets in question
            pii_entities = []
            for placeholder, pii_type in tmpl["pii"]:
                val = values[placeholder]
                try:
                    s, e = _find(question, val)
                    pii_entities.append(_ent(pii_type, val, s, e))
                except AssertionError:
                    pass  # value not in question (shouldn't happen)

            rows.append({
                "id": f"pii_qa_{idx:03d}",
                "question": question,
                "expected_answer": answer,
                "pii_entities": pii_entities,
                "category": tmpl["cat"],
            })

    # Add control group (no PII)
    for tmpl in CONTROL_TEMPLATES:
        idx += 1
        rows.append({
            "id": f"pii_qa_{idx:03d}",
            "question": tmpl["q"],
            "expected_answer": tmpl["a"],
            "pii_entities": [],
            "category": tmpl["cat"],
        })

    return rows


def write_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    rows = generate_dataset()
    write_jsonl(rows, OUT)

    # Print statistics
    total = len(rows)
    pii_rows = [r for r in rows if r["pii_entities"]]
    ctrl_rows = [r for r in rows if not r["pii_entities"]]
    cats = {}
    pii_types = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
        for e in r["pii_entities"]:
            pii_types[e["type"]] = pii_types.get(e["type"], 0) + 1

    pii_in_answer = sum(1 for r in pii_rows
                        if any(e["value"] in r["expected_answer"] for e in r["pii_entities"]))

    print(f"Generated {total} samples → {OUT}")
    print(f"  PII samples: {len(pii_rows)} ({len(pii_rows)/total*100:.1f}%)")
    print(f"  Control (no PII): {len(ctrl_rows)} ({len(ctrl_rows)/total*100:.1f}%)")
    print(f"  PII in answer: {pii_in_answer} ({pii_in_answer/len(pii_rows)*100:.1f}% of PII samples)")
    print(f"\nCategory distribution:")
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt}")
    print(f"\nPII type distribution:")
    for pt, cnt in sorted(pii_types.items()):
        print(f"  {pt}: {cnt}")


if __name__ == "__main__":
    main()
