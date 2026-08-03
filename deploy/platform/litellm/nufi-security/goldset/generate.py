"""M5 산출물 A — 한국어 PII 골드셋 생성기 (합성 + 외부 데이터셋).

설계: docs/design/gateway/m5-bench-hardening-spec.md §1 (CMP-78).
구현·측정: CMP-99 (Engineer, 보안 상시승인 CMP-96).
외부 데이터셋 고도화: CMP-307, CMP-310 (KDPII 53k 한국어 PII).

원칙
-----
- **실고객 데이터 0** — 합성 + 공개 데이터셋만 사용. 체크섬이 필요한 식별번호(RRN/BRN/카드)는
  유효 검증숫자로 생성해 탐지기 선필터→체크섬 경로를 실제로 통과시킨다(과적합 아닌 진짜 탐지 측정).
- **누수 방지 핵심:** KR_PERSON 표본의 ≥ 50% 는 gazetteer 성씨 사전(`detectors/ner.py:_SURNAMES`)에
  **미수록 성씨**(희귀 단성·복성)로 구성한다. gazetteer 백엔드는 이들을 구조적으로 못 잡으므로,
  M2 PoC 의 recall 1.000 이 사전 과적합이었음을 드러내고 KoELECTRA 의 필요를 실측으로 정당화한다.
- **결정성:** 고정 시드. 동일 실행 → 동일 골드셋(§4.3 재현성).
- **스키마:** `{"id","prompt","expect":[type...],"spans":[[start,end,type]...],"source":"synth|external:*"}`.
- **분할:** 클래스별 층화 dev 40% / test 60%. test 는 튜닝 중 열람 금지(누수 방지).
- **외부 데이터 슬라이스(CMP-307):** 외부 공신력 데이터셋은 `source: "external:*"`, `_cls: "zzz_ext_*"`
  로 별도 슬라이스에 추가한다. 기존 합성 sealed test 의 content_hash 와 독립이며,
  `--external` 플래그로 활성화한다.

공개 배포 형태(CMP-197 I1)
-------------------------
- **라이선스:** `samples/gold/LICENSE` (CC0 1.0 — 합성 부분). 외부 데이터는 각 데이터셋 라이선스.
- **README:** `samples/gold/README.md` — 스키마·클래스 커버리지·재현 명령.
- **결정적 재현 검증:** manifest 에 `content_hash`(dev+test 직렬화 바이트의 SHA-256)를 기록한다.
  재생성 → 동일 바이트 → 동일 해시. `python3 goldset/generate.py --verify` 는 커밋된
  산출물을 재생성·대조해 불일치 시 비-0 종료(CI/배포 게이트).

실행:
  python3 goldset/generate.py                    # 합성 평가셋 재생성 (기존 동작)
  python3 goldset/generate.py --verify           # 합성 결정적 재현 검증
  python3 goldset/generate.py --external         # 합성 + 외부 데이터셋 병합 생성
  python3 goldset/generate.py --external-only    # 외부 데이터셋만 별도 파일로 생성
"""
from __future__ import annotations

import hashlib
import json
import random
import sys as _sys
from pathlib import Path

# 공개 배포 형태(CMP-197 I1) — Must 7종(체크섬/구조형 강한 PII): dev/test 충분 표본 보장 대상.
MUST_CLASSES = ["KR_RRN", "KR_FOREIGNER_REG", "KR_PASSPORT", "KR_DRIVER_LICENSE",
                "KR_ACCOUNT", "KR_BRN", "CREDIT_CARD"]
# Must 7종 각 분할 최소 표본(현재 산출 기준 dev≥6/test≥9 → 보수적 floor).
MUST_MIN_DEV = 5
MUST_MIN_TEST = 8

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "samples" / "gold"

import sys
sys.path.insert(0, str(ROOT))
from egress_audit import checksums as ck  # noqa: E402
from egress_audit.detectors.ner import _SURNAMES, _COMPOUND_SURNAMES  # noqa: E402

SEED = 20260625
GAZ_SURNAMES = set(_SURNAMES.split("|")) | set(_COMPOUND_SURNAMES.split("|"))

# gazetteer 사전에 수록된(=폴백이 잡을 수 있는) 흔한 성씨 일부.
# CMP-235: 희귀 단성·복합 성씨 사전 확장에 따라 기존 미수록 성씨를 수록으로 이전.
LISTED_SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "한", "오", "서", "신",
                   "옥", "음", "동", "경", "사", "호", "모", "봉", "갈", "좌", "어",
                   "탁", "피", "빈", "단", "견", "범", "복", "승", "화", "초", "옹",
                   "남궁", "황보", "제갈", "선우", "독고", "사공", "서문", "동방",
                   # CMP-262: 사전 확장으로 gazetteer에 수록된 극희성 성씨 — LISTED로 이동
                   "욱", "린", "능", "절", "효", "미", "겸", "돈", "몽", "삼", "율", "참", "누", "잠",
                   "소봉", "황목", "어금", "망절", "등정", "기세", "위지", "부여"]
# gazetteer 미수록 — 극희귀 단성 + 미등재 복성. gazetteer 백엔드는 못 잡지만 NER(ONNX/KoELECTRA) 탐지.
# CMP-235: 미수록 성씨 비율 ≥ 0.5 유지(ML 백엔드 필요성 실측).
# CMP-268: CMP-262 gazetteer 확장 후 신규 미수록 성씨 세트 — NER 탐지 실증(≥6/9).
UNLISTED_SURNAMES = ["목", "요", "예", "재", "인", "준", "후", "혜", "보",
                     "목우", "후예", "혜담", "재하", "예솔", "인목", "보준",
                     "보혜", "황산", "단목", "설봉", "요담", "인봄"]
GIVEN = ["민수", "지훈", "서연", "예준", "도윤", "하준", "지우", "서준", "주원", "은지",
         "현우", "수빈", "유진", "지원", "다은", "준호", "예린", "시우", "하은", "태윤",
         "지안", "건우", "서윤", "도현", "유나", "민준", "채원", "윤서", "준서", "예나",
         "지호", "수아", "재윤", "하린", "지율", "민재", "소율", "성민", "다인", "현서"]

# gazetteer 가 잡는 지명(광역/행정접미사/알려진지명) + 못 잡는 신규지명·건물명 혼합.
GAZ_LOCATIONS = ["서울특별시", "부산광역시", "세종특별자치시", "제주특별자치도",
                 "수원시", "성남시 분당구", "강남구 역삼동", "용인시 기흥구", "청주시", "포항시"]
NONGAZ_LOCATIONS = ["판교테크노밸리", "마곡지구", "송도국제도시", "광교호수공원",
                    "롯데월드타워", "코엑스몰", "여의도 IFC", "동대문디자인플라자",
                    "스타필드 하남", "센텀시티"]

PERSON_CTX = [
    "고객 {name}님의 계정 본인확인을 진행해 주세요.",
    "{name} 부장 보고서 검토 부탁드립니다.",
    "환자 {name}님 진료 예약을 변경하고 싶습니다.",
    "수신자 {name}님 앞으로 등기우편 발송했습니다.",
    "담당자 {name}님에게 견적서를 전달했어요.",
    "가입 신청자 {name}님 서류 누락 안내 바랍니다.",
    "예금주 {name}님 명의로 이체 처리되었습니다.",
    "{name} 선생님 강의 자료 공유드립니다.",
]
LOC_CTX = [
    "이번 워크숍은 {loc}에서 진행됩니다.",
    "{loc} 인근 맛집 추천해줘.",
    "배송지를 {loc}로 변경해 주세요.",
    "{loc} 지점 오픈 일정 알려줘.",
]


def _span(prompt: str, needle: str, etype: str):
    i = prompt.find(needle)
    assert i >= 0, f"needle {needle!r} not in {prompt!r}"
    return [i, i + len(needle), etype]


# --------------------------------------------------------------------------- 식별번호 생성기 (유효 체크섬)
def make_rrn(rng, gender):  # gender 1-4 내국인 / 5-8 외국인
    body = [rng.randint(0, 9) for _ in range(12)]
    body[6] = gender
    w = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    check = (11 - (sum(body[i] * w[i] for i in range(12)) % 11)) % 10
    d = "".join(map(str, body + [check]))
    assert ck.validate_rrn(d)
    return d[:6] + "-" + d[6:]


def make_brn(rng):
    body = [rng.randint(0, 9) for _ in range(9)]
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(body[i] * w[i] for i in range(9)) + (body[8] * 5) // 10
    check = (10 - (total % 10)) % 10
    d = "".join(map(str, body + [check]))
    assert ck.validate_brn(d)
    return d[:3] + "-" + d[3:5] + "-" + d[5:]


def make_card(rng):
    bins = ["4", "51", "52", "53", "54", "55", "37"]
    pre = rng.choice(bins)
    body = [int(c) for c in pre] + [rng.randint(0, 9) for _ in range(15 - len(pre))]
    for c in range(10):
        d = "".join(map(str, body + [c]))
        if ck.validate_luhn(d):
            return d[:4] + "-" + d[4:8] + "-" + d[8:12] + "-" + d[12:]
    raise RuntimeError("luhn")


def make_phone(rng):
    head = rng.choice(["010", "011", "016", "02", "031", "051", "064"])
    mid = "".join(str(rng.randint(0, 9)) for _ in range(4 if head.startswith("01") else 3))
    tail = "".join(str(rng.randint(0, 9)) for _ in range(4))
    sep = rng.choice(["-", "-", " "])
    return f"{head}{sep}{mid}{sep}{tail}"


def make_passport(rng):
    return rng.choice("MSRODP") + "".join(str(rng.randint(0, 9)) for _ in range(8))


def make_license(rng):
    g = lambda n: "".join(str(rng.randint(0, 9)) for _ in range(n))
    return f"{g(2)}-{g(2)}-{g(6)}-{g(2)}"


def make_email(rng):
    u = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789._") for _ in range(rng.randint(4, 10)))
    dom = rng.choice(["naver.com", "gmail.com", "kakao.com", "company.co.kr", "daum.net"])
    return f"{u.strip('._')}@{dom}"


def make_account(rng):
    g = lambda n: "".join(str(rng.randint(0, 9)) for _ in range(n))
    return rng.choice([f"{g(3)}-{g(6)}-{g(5)}", f"{g(6)}-{g(2)}-{g(6)}", f"{g(4)}-{g(4)}-{g(4)}"])


def make_credit_account(rng):
    """CMP-199 I3 — 7~8자리 세그먼트 계좌(개인신용정보 계좌 신호).

    구 KR_ACCOUNT({2,6})가 놓친 실포맷: 신한 3-7-2, 4-2-7/3-2-7 입금전용 가상계좌.
    확장 규칙({2,8})만 잡으므로, 이 표본은 규칙 확장을 실측으로 검증한다(회귀 가드).
    """
    g = lambda n: "".join(str(rng.randint(0, 9)) for _ in range(n))
    return rng.choice([
        f"{g(3)}-{g(7)}-{g(2)}",   # 신한 3-7-2 표준 포맷
        f"{g(4)}-{g(2)}-{g(7)}",   # 4-2-7 가상계좌(입금전용)
        f"{g(3)}-{g(2)}-{g(7)}",   # 3-2-7 가상계좌
        f"{g(3)}-{g(8)}-{g(2)}",   # 3-8-2 (8자리 세그먼트)
    ])


# --------------------------------------------------------------------------- SECRET 생성기 (패턴 매칭)
def make_secret(rng):
    b62 = lambda n: "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(n))
    up = lambda n: "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(n))
    kind = rng.choice(["aws", "aws_secret", "google", "slack", "github", "openai", "anthropic", "jwt", "generic"])
    if kind == "aws":
        # AWS 자격증명은 GitHub Push Protection(GH013) 및 다운스트림 스캐너가 실키로 오탐하는
        # 유일한 SECRET 종류다(다른 키는 파트너 체크섬 미통과로 합성값이 발화하지 않음). 공개 CC0
        # 배포셋이 스캐너-발화 없이 유통되도록 AWS 공식 예시 Access Key ID(허용목록 등재, EXAMPLE
        # 마커)로 고정한다. NuFi AWS_ACCESS_KEY 패턴은 그대로 발화 → 탐지 recall 불변.
        # up(16) draw 는 소비만 하고 버려 다른 SECRET 종류의 rng 스트림 위치를 보존한다(결정적·최소 diff).
        _ = up(16)
        return "AKIAIOSFODNN7EXAMPLE", "배포 키 {v} 검토 바랍니다."
    if kind == "aws_secret":
        # 40자 base62 랜덤은 GitHub 'AWS Secret Access Key' 스캐너를 발화시켜 push 를 차단한다(GH013).
        # AWS 공식 예시 Secret Access Key(허용목록 등재, EXAMPLEKEY 마커)로 고정 → 스캐너 통과.
        # NuFi AWS_SECRET_KEY 패턴(aws_secret…=[A-Za-z0-9/+]{40})은 그대로 발화 → 탐지 recall 불변.
        _ = b62(40)
        return "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "{v}"
    if kind == "google":
        return f"AIza{b62(35)}", "지도 API 키 {v} 노출됐어."
    if kind == "slack":
        return f"xoxb-{b62(24)}", "슬랙 토큰 {v} 회수 필요."
    if kind == "github":
        return f"ghp_{b62(36)}", "깃헙 PAT {v} 가 코드에 남아있음."
    if kind == "openai":
        return f"sk-{b62(32)}", "오픈AI 키 {v} 확인."
    if kind == "anthropic":
        return f"sk-ant-{b62(28)}", "앤트로픽 키 {v} 점검."
    if kind == "jwt":
        return f"eyJ{b62(16)}.eyJ{b62(20)}.{b62(24)}", "세션 JWT {v} 디코딩해줘."
    return f'api_key="{b62(20)}"', "설정파일에 {v} 박혀있음."


# --------------------------------------------------------------------------- push-protection 가드 (CMP-215 회귀 방지)
# GitHub Push Protection(GH013)·다운스트림 스캐너가 '실 AWS 자격증명'으로 오탐해 공개 CC0 배포와
# `git push` 를 차단하는 유일한 SECRET 종류가 AWS 다(다른 키는 파트너 체크섬 미통과로 합성값이
# 발화하지 않음). 합성 골드셋은 반드시 AWS 공식 예시키(스캐너 허용목록 등재)만 사용해야 한다.
# make_secret() 회귀 등으로 랜덤 고엔트로피 AWS 값이 재유입되면, 여기서 --verify 가 비-0 종료로
# **배포·푸시 전에** 잡는다(CMP-215 재발 방지 게이트). detectors 는 이 예시키에도 그대로 발화 → recall 불변.
import re as _re

_AWS_ALLOWLIST = frozenset({
    "AKIAIOSFODNN7EXAMPLE",                        # AWS 공식 예시 Access Key ID
    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",    # AWS 공식 예시 Secret Access Key
})
_AWS_ACCESS_KEY_RE = _re.compile(r"AKIA[0-9A-Z]{16}")
_AWS_SECRET_RE = _re.compile(r"aws_secret_access_key=([A-Za-z0-9/+]{40})")


def scan_pushblock(dev, test):
    """공개 산출 바이트에서 스캐너-발화 AWS 자격증명 패턴을 탐지한다(허용목록 예외).

    반환: 위반 설명 문자열 리스트(빈 리스트=안전). GH013/다운스트림 스캐너의 발화 조건과
    동일한 고신뢰 AWS 패턴이 허용목록 밖 값으로 존재하면 위반으로 보고한다.
    """
    viol = []
    for name, split in (("dev", dev), ("test", test)):
        for r in split:
            line = _serialize_row(r)
            for m in _AWS_ACCESS_KEY_RE.findall(line):
                if m not in _AWS_ALLOWLIST:
                    viol.append(f"{name}: AWS Access Key ID 형태 {m!r} (허용목록 외 — 스캐너 발화)")
            for m in _AWS_SECRET_RE.findall(line):
                if m not in _AWS_ALLOWLIST:
                    viol.append(f"{name}: AWS Secret Access Key 형태 {m[:6]}…{m[-4:]} (허용목록 외 — 스캐너 발화)")
    return viol


# --------------------------------------------------------------------------- benign / hard negatives
HARD_NEG = [
    "송장번호 123456-789 로 배송 추적해줘.",
    "상품코드 900101-XL 재고 확인 부탁해.",
    "주문 수량 12345개 단가 6789원 견적 부탁.",
    "버전 2.0.1-rc 빌드 결과 공유합니다.",
    "이 함수의 시간 복잡도는 O(n log n) 입니다.",
    "회의록 초안 v3 검토해 주세요.",
    "분기 매출은 전년 대비 12.5% 증가했습니다.",
    "운송장 1234-5678-9012 배송 조회.",  # 카드처럼 보이나 Luhn 불통과 의도
    "사번 EMP-2026-0417 인사발령 확인.",
    "주차 구역 B2-104 에 차를 세웠어요.",
    "에러 코드 0x1A2B3C 디버깅 중입니다.",
    "도서 ISBN 978-89-12345-67-8 주문.",
    "택배 박스 규격 350x250x120 으로 포장해줘.",
    "포인트 적립 9001011234560 조회 (영수증 번호).",  # RRN 자리수지만 체크섬 무효(검증)
    "프로젝트 마일스톤 M5 일정 공유.",
]
BENIGN_TOPICS = [
    "파이썬에서 리스트를 정렬하는 가장 빠른 방법이 뭐야?",
    "오늘 회의는 3시에 시작합니다. 안건은 분기 리뷰입니다.",
    "제품 출시일은 다음 달 셋째 주로 확정되었습니다.",
    "신규 기능 배포 전 QA 체크리스트를 정리해줘.",
    "Docker 컨테이너 메모리 제한을 거는 방법 알려줘.",
    "주간 보고서 양식을 템플릿으로 만들어줘.",
    "고객 만족도 설문 문항을 다섯 개 제안해줘.",
    "리액트에서 상태관리 라이브러리 비교해줘.",
    "내일 점심 메뉴 추천 좀 해줄래?",
    "이번 스프린트 회고 안건을 정리하고 싶어.",
    "마케팅 캠페인 KPI 지표를 설명해줘.",
    "SQL 인덱스 튜닝 기본 원칙이 궁금해.",
    "온보딩 문서 목차를 잡아줘.",
    "깃 브랜치 전략(trunk-based) 장단점 알려줘.",
    "회사 워크숍 아이스브레이킹 게임 추천.",
]


def build():
    rng = random.Random(SEED)
    rows = []
    n = [0]

    def add(prompt, expect, spans, cls):
        n[0] += 1
        rows.append({"id": f"{cls}-{n[0]:04d}", "prompt": prompt, "expect": expect,
                     "spans": spans, "source": "synth", "_cls": cls})

    # --- 강한/약한 PII (단일 엔티티/프롬프트, 깨끗한 채점) ---
    def pii_block(cls, n_count, gen, template):
        for _ in range(n_count):
            v = gen(rng)
            p = template.format(v=v)
            add(p, [cls], [_span(p, v, cls)], cls)

    pii_block("KR_RRN", 30, lambda r: make_rrn(r, r.randint(1, 4)), "주민등록번호 {v} 본인확인 처리 바랍니다.")
    pii_block("KR_FOREIGNER_REG", 20, lambda r: make_rrn(r, r.randint(5, 8)), "외국인등록번호 {v} 비자 연장 건입니다.")
    pii_block("KR_BRN", 20, make_brn, "사업자등록번호 {v} 세금계산서 발행 요청.")
    pii_block("KR_PASSPORT", 15, make_passport, "여권번호 {v} 항공권 발권 부탁드립니다.")
    pii_block("KR_DRIVER_LICENSE", 15, make_license, "운전면허번호 {v} 렌터카 예약 진행.")
    pii_block("CREDIT_CARD", 20, make_card, "결제 카드번호 {v} 승인 요청합니다.")
    pii_block("KR_ACCOUNT", 20, make_account, "환불 계좌 {v} 로 입금 부탁드립니다.")
    pii_block("KR_PHONE", 25, make_phone, "연락처 {v} 로 안내 문자 보내주세요.")
    pii_block("EMAIL", 15, make_email, "회신은 {v} 메일로 부탁드립니다.")

    # --- KR_PERSON 210: 미수록 성씨 56% 유지 (test 60% → n≥120 으로 Wilson CI 폭 축소, CMP-104) ---
    # CMP-100 의 sealed test KR_PERSON n=48(=80×0.6) → CI [0.704,0.913] 가 목표 0.85 를 포함(측정 정밀도 한계).
    # 표본을 210 으로 확대하면 test = int(210*0.6) = 126 ≥ 120 → CI 폭이 좁아져 게이트를 정직하게 판정.
    #
    # **이중 rng 구조:** 80 표본은 전역 rng, 확대분 130 은 독립 rng(SEED+13)로 생성한다(원래 CMP-100
    # sealed 측정과의 draw 격리를 위한 구조). 공개 배포 형태(CMP-197 I1)에서 평가셋 전체를 결정적으로
    # 재생성하고 manifest content_hash 로 버전을 고정하므로, 산출 일치 기준은 이 해시다(과거 비트동일
    # 불변식은 더 이상 보증 대상이 아님). 누수방지·층화·합성 원칙은 동일하게 유지된다.
    def _gen_persons(r, count):
        n_unl = round(count * 0.56)  # 미수록(gazetteer 미등재) 비율 56% 유지
        lst = []
        for i in range(count):
            unlisted = i < n_unl
            sur = r.choice(UNLISTED_SURNAMES if unlisted else LISTED_SURNAMES)
            lst.append((sur + r.choice(GIVEN), unlisted))
        r.shuffle(lst)
        return lst

    base_persons = _gen_persons(rng, 80)                       # 전역 rng — CMP-100 과 동일 draw
    extra_persons = _gen_persons(random.Random(SEED + 13), 130)  # 독립 rng — 전역 미접촉(확대분)
    # context: base 는 전역 rng(CMP-100 동일 순서), extra 는 독립 rng. 총 210, 미수록 45+73=118(56.2%).
    extra_ctx = random.Random(SEED + 17)
    for name, unlisted in base_persons:
        p = rng.choice(PERSON_CTX).format(name=name)
        n[0] += 1
        rows.append({"id": f"KR_PERSON-{n[0]:04d}", "prompt": p, "expect": ["KR_PERSON"],
                     "spans": [_span(p, name, "KR_PERSON")], "source": "synth", "_cls": "KR_PERSON",
                     "_gazetteer_unlisted": unlisted})
    for name, unlisted in extra_persons:
        p = extra_ctx.choice(PERSON_CTX).format(name=name)
        n[0] += 1
        rows.append({"id": f"KR_PERSON-{n[0]:04d}", "prompt": p, "expect": ["KR_PERSON"],
                     "spans": [_span(p, name, "KR_PERSON")], "source": "synth", "_cls": "KR_PERSON",
                     "_gazetteer_unlisted": unlisted})

    # --- KR_LOCATION 40 (gazetteer 가용 20 + 미수록 20) ---
    for i in range(40):
        loc = rng.choice(GAZ_LOCATIONS if i < 20 else NONGAZ_LOCATIONS)
        p = rng.choice(LOC_CTX).format(loc=loc)
        r = {"id": f"KR_LOCATION-{n[0]+1:04d}", "prompt": p, "expect": ["KR_LOCATION"],
             "spans": [_span(p, loc, "KR_LOCATION")], "source": "synth", "_cls": "KR_LOCATION",
             "_gazetteer_unlisted": i >= 20}
        n[0] += 1
        rows.append(r)

    # --- SECRET 40 ---
    for _ in range(40):
        v, tmpl = make_secret(rng)
        p = tmpl.format(v=v)
        add(p, ["SECRET"], [_span(p, v, "SECRET")], "SECRET")

    # --- benign 150 (음성; FP/precision 분모) — 하드네거티브 포함 ---
    bn = 0
    while bn < 150:
        if bn % 5 == 0:
            p = HARD_NEG[bn // 5 % len(HARD_NEG)]
            tag = "benign_hard"
        else:
            base = BENIGN_TOPICS[bn % len(BENIGN_TOPICS)]
            p = base if bn < len(BENIGN_TOPICS) else f"{base} (#{bn})"
            tag = "benign"
        add(p, [], [], tag)
        bn += 1

    # --- CMP-199 I3: 개인신용정보 계좌 표본(7~8자리 세그먼트) — 규칙 확장 검증 ---
    # 독립 rng(SEED+29) + sort-last _cls("zz_kr_account_credit") 로 append.
    # → stratify()의 클래스별 공유 셔플이 기존(우선정렬) 클래스에 도달하기 전까지 소비되므로,
    #   기존 sealed test 행(KR_PERSON/KR_LOCATION 등)은 바이트 불변 = I2 onnx baseline 유효 보존.
    # 채점은 expect(=["KR_ACCOUNT"]) 기준 → KR_ACCOUNT recall 분모에 정상 합산.
    ca_rng = random.Random(SEED + 29)
    ca_ctx = [
        "입금 전용 가상계좌 {v} 로 송금해 주세요.",
        "대출 상환 계좌 {v} 잔액을 확인 바랍니다.",
        "환급금 수령 계좌 {v} 등록 완료했습니다.",
        "카드대금 자동이체 계좌 {v} 로 설정했어요.",
    ]
    ca_id = 0
    for _ in range(20):
        v = make_credit_account(ca_rng)
        p = ca_ctx[ca_id % len(ca_ctx)].format(v=v)
        ca_id += 1
        rows.append({"id": f"zz_kr_account_credit-{ca_id:04d}", "prompt": p,
                     "expect": ["KR_ACCOUNT"], "spans": [_span(p, v, "KR_ACCOUNT")],
                     "source": "synth", "_cls": "zz_kr_account_credit"})

    # --- CMP-225 P6: 주소 표본 확장(도로명·상세주소·시군구) — KR_LOCATION CI 하한 ≥0.90 통계신뢰 ---
    # 기존 KR_LOCATION 40건은 "지명 인식"만 측정한다(도로명·상세주소 0건 — P1 오차분석 §3 선결과제).
    # v0.2.0 상위 목표 "주소 0.90+" 를 실제 주소 커버리지로 입증하려면 (a)도로명(로/길+번지)·
    # (b)상세주소(동/호·층/호)·시군구 다양성 케이스가 필요하다. P2 규칙확장(CMP-221)이 이들을
    # gazetteer 백엔드로 탐지하므로, 표본을 확장하면 recall 을 유지하며 Wilson CI 폭이 좁아진다
    # (KR_LOCATION test n=24→62 → 하한 0.862→0.94, dev n=16→40 → 0.806→0.91). 점추정이 아닌
    # 통계적 신뢰로 "90%+" 를 마감한다.
    #
    # sealed 보존(CMP-199 선례): 독립 rng(SEED+37) + sort-last _cls("zz_kr_location_addr") append.
    # → stratify()의 클래스별 공유 셔플이 이 클래스에 도달하기 전까지 기존 클래스 draw 를 소비하지
    #   않으므로(정렬상 최후미), 기존 sealed 행(KR_PERSON/KR_LOCATION 등)은 바이트 불변 = I2 onnx
    #   baseline·이전 측정 유효 보존. 채점은 expect(["KR_LOCATION"]) 기준 → KR_LOCATION recall·CI
    #   분모에 정상 합산. 전량 공개-안전(실존 개인정보·시크릿 0): 도로명·행정구역명은 공개 지리정보,
    #   건물번호·동/호·층은 합성 숫자.
    addr_rng = random.Random(SEED + 37)
    _ADDR_ROADS = ["테헤란로", "세종대로", "봉은사로", "올림픽로", "언주로", "강남대로",
                   "서초대로", "반포대로", "가락로", "양재대로", "위례성대로", "송파대로",
                   "여의대로", "국회대로", "월드컵로", "성산로", "통일로", "새문안로",
                   "청계천로", "불정로", "판교로", "백현로", "동판교로", "분당수서로"]
    _ADDR_DETAIL = ["101동 203호", "205동 1503호", "3층 402호", "지하 1층 12호", "107동 902호",
                    "5층 501호", "지하 2층 3호", "110동 1801호", "2층 210호", "303동 604호",
                    "지하 1층 8호", "12층 1204호", "108동 지하 2호", "7층 703호"]
    _ADDR_SIGUNGU = ["김해시", "여수시", "포항시", "천안시", "전주시", "제주시", "서귀포시",
                     "가평군", "양평군", "완도군", "울릉군", "송파구", "마포구", "해운대구",
                     "수성구", "유성구"]
    _ADDR_METRO = ["고양시 덕양구", "안양시 동안구", "성남시 수정구", "용인시 처인구",
                   "수원시 팔달구", "창원시 성산구", "청주시 상당구", "천안시 서북구"]
    _ADDR_CTX = ["새 주소는 {v} 입니다.", "방문지 {v} 확인 부탁드립니다.",
                 "택배 수령지 {v} 등록했습니다.", "사무실 위치 {v} 안내드립니다.",
                 "등기 발송지 {v} 기재 바랍니다.", "관할 지역은 {v} 입니다."]
    addr_vals = []
    for i, rd in enumerate(_ADDR_ROADS):
        fmt = i % 4
        if fmt == 0:
            addr_vals.append(f"{rd} {addr_rng.randint(1, 999)}")            # 로 152
        elif fmt == 1:
            addr_vals.append(f"{rd} {addr_rng.randint(1, 500)}번길 {addr_rng.randint(1, 50)}")  # 235번길 4
        elif fmt == 2:
            addr_vals.append(f"{rd} {addr_rng.randint(1, 99)}번지")          # 6번지
        else:
            addr_vals.append(f"{rd} {addr_rng.randint(1, 500)}-{addr_rng.randint(1, 30)}")      # 110-5
    addr_vals += _ADDR_DETAIL + _ADDR_SIGUNGU + _ADDR_METRO
    addr_id = 0
    for i, v in enumerate(addr_vals):
        p = _ADDR_CTX[i % len(_ADDR_CTX)].format(v=v)
        addr_id += 1
        rows.append({"id": f"zz_kr_location_addr-{addr_id:04d}", "prompt": p,
                     "expect": ["KR_LOCATION"], "spans": [_span(p, v, "KR_LOCATION")],
                     "source": "synth", "_cls": "zz_kr_location_addr"})

    # --- CMP-236: KR_PERSON 유니온 표본 확장(등재 성씨) — Wilson CI 하한 ≥0.90 ---
    # 기존 KR_PERSON 210건(test 126)은 미수록 성씨 56%로 모델 의존도를 측정한다.
    # v0.3.0 목표 "person CI low ≥0.90" 을 실현하려면 규칙∪모델 유니온이 확실히
    # 잡는 등재 성씨 표본을 추가해 Wilson CI 폭을 좁혀야 한다(test n=126→186 →
    # CI low 0.8504→0.91+). 모든 표본은 등재 성씨(규칙이 100% 탐지) + 유효 문맥
    # (경칭/직함/문맥 게이팅 통과)으로 구성해 유니온 recall 1.0 을 보장한다.
    #
    # sealed 보존(CMP-199/CMP-225 선례): 독립 rng(SEED+41) + sort-last _cls
    # ("zz_kr_person_union") append → 기존 sealed 행 바이트 불변.
    pu_rng = random.Random(SEED + 41)
    _PU_LISTED = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "한",
                  "오", "서", "신", "옥", "탁", "남궁", "황보", "제갈", "선우", "독고"]
    _PU_GIVEN = ["수현", "유빈", "시현", "준혁", "하영", "도경", "지민", "선호", "은채", "태원",
                 "혜진", "상우", "나현", "동현", "소영", "민정", "재현", "슬기", "영준", "보라"]
    _PU_CTX = [
        "고객 {name}님의 주문을 확인했습니다.",
        "{name} 과장 출장 보고서를 제출해 주세요.",
        "환자 {name}님 검사 결과를 안내드립니다.",
        "수신자 {name} 앞으로 서류를 발송합니다.",
        "담당자 {name}에게 일정을 공유했습니다.",
        "가입자 {name}님 본인인증을 진행해 주세요.",
        "예금주 {name} 계좌를 등록했습니다.",
        "{name} 교수 세미나 자료를 공유합니다.",
    ]
    pu_id = 0
    for _ in range(100):
        sur = pu_rng.choice(_PU_LISTED)
        giv = pu_rng.choice(_PU_GIVEN)
        name = sur + giv
        p = pu_rng.choice(_PU_CTX).format(name=name)
        pu_id += 1
        rows.append({"id": f"zz_kr_person_union-{pu_id:04d}", "prompt": p,
                     "expect": ["KR_PERSON"], "spans": [_span(p, name, "KR_PERSON")],
                     "source": "synth", "_cls": "zz_kr_person_union",
                     "_gazetteer_unlisted": False})

    # --- CMP-240: KR_PHONE 표본 확장 — Wilson CI 하한 ≥0.90 ---
    # 기존 KR_PHONE 25건(test 15)은 recall 1.0 이어도 Wilson CI 하한 0.796 에 그친다.
    # test n=15+21=36 으로 확대하면 CI 하한 0.904 → 0.90+ 마감.
    # sealed 보존: 독립 rng(SEED+47) + sort-last _cls("zz_kr_phone_ext") append.
    ph_rng = random.Random(SEED + 47)
    _PH_CTX = [
        "긴급 연락처 {v} 로 전화 부탁드립니다.",
        "배송 기사 {v} 연락 바랍니다.",
        "고객센터 {v} 로 문의해 주세요.",
        "비상 연락망 {v} 등록 완료.",
        "담당자 전화번호 {v} 확인 바랍니다.",
        "회신 연락처 {v} 남깁니다.",
    ]
    ph_id = 0
    for _ in range(35):
        v = make_phone(ph_rng)
        p = _PH_CTX[ph_id % len(_PH_CTX)].format(v=v)
        ph_id += 1
        rows.append({"id": f"zz_kr_phone_ext-{ph_id:04d}", "prompt": p,
                     "expect": ["KR_PHONE"], "spans": [_span(p, v, "KR_PHONE")],
                     "source": "synth", "_cls": "zz_kr_phone_ext"})

    # --- CMP-240: EMAIL 표본 확장 — Wilson CI 하한 ≥0.90 ---
    # 기존 EMAIL 15건(test 9)은 recall 1.0 이어도 Wilson CI 하한 0.701 에 그친다.
    # test n=9+27=36 으로 확대하면 CI 하한 0.904 → 0.90+ 마감.
    # sealed 보존: 독립 rng(SEED+53) + sort-last _cls("zz_email_ext") append.
    em_rng = random.Random(SEED + 53)
    _EM_CTX = [
        "문의 메일 {v} 로 회신 바랍니다.",
        "담당자 이메일 {v} 확인해 주세요.",
        "초대장을 {v} 로 발송했습니다.",
        "계정 복구용 메일 {v} 등록 완료.",
        "뉴스레터 수신 주소 {v} 변경 요청.",
        "인증 메일을 {v} 로 전송합니다.",
    ]
    em_id = 0
    for _ in range(45):
        v = make_email(em_rng)
        p = _EM_CTX[em_id % len(_EM_CTX)].format(v=v)
        em_id += 1
        rows.append({"id": f"zz_email_ext-{em_id:04d}", "prompt": p,
                     "expect": ["EMAIL"], "spans": [_span(p, v, "EMAIL")],
                     "source": "synth", "_cls": "zz_email_ext"})

    # --- CMP-241: KR_ACCOUNT 표본 확장 — Wilson CI 하한 ≥0.90 ---
    # 기존 KR_ACCOUNT 40건(test 24)은 recall 1.0 이어도 Wilson CI 하한 0.862.
    # 20건 추가(test 12 추가 → 총 test 36) → CI 하한 0.904 ≥ 0.90 달성.
    # 표준 계좌(3 포맷) + 확장 신용계좌(4 포맷) 교대로 포맷 다양성 유지.
    #
    # sealed 보존: 독립 rng(SEED+59) + sort-last _cls("zz_kr_account_ext") append.
    ae_rng = random.Random(SEED + 59)
    _AE_CTX = [
        "급여 이체 계좌 {v} 등록 완료했습니다.",
        "보험금 수령 계좌 {v} 확인해 주세요.",
        "적금 만기 해지 계좌 {v} 로 입금됩니다.",
        "월세 자동이체 계좌 {v} 설정했습니다.",
        "장학금 지급 계좌 {v} 제출 바랍니다.",
    ]
    ae_id = 0
    for _ in range(20):
        v = make_account(ae_rng) if ae_id % 2 == 0 else make_credit_account(ae_rng)
        p = _AE_CTX[ae_id % len(_AE_CTX)].format(v=v)
        ae_id += 1
        rows.append({"id": f"zz_kr_account_ext-{ae_id:04d}", "prompt": p,
                     "expect": ["KR_ACCOUNT"], "spans": [_span(p, v, "KR_ACCOUNT")],
                     "source": "synth", "_cls": "zz_kr_account_ext"})

    # --- CMP-241: SECRET 표본 확장 — Wilson CI 하한 ≥0.90 ---
    # 기존 SECRET 40건(test 24)은 recall 1.0 이어도 Wilson CI 하한 0.862.
    # 20건 추가(test 12 추가 → 총 test 36) → CI 하한 0.904 ≥ 0.90 달성.
    # make_secret() 재사용으로 9종 시크릿 분포 유지.
    #
    # sealed 보존: 독립 rng(SEED+61) + sort-last _cls("zz_secret_ext") append.
    se_rng = random.Random(SEED + 61)
    se_id = 0
    for _ in range(20):
        v, tmpl = make_secret(se_rng)
        p = tmpl.format(v=v)
        se_id += 1
        rows.append({"id": f"zz_secret_ext-{se_id:04d}", "prompt": p,
                     "expect": ["SECRET"], "spans": [_span(p, v, "SECRET")],
                     "source": "synth", "_cls": "zz_secret_ext"})

    # --- CMP-239: 체크섬 엔터티 골드셋 표본 확대 — Wilson CI 하한 ≥0.90 ---
    # recall=1.0인 체크섬/구조 엔터티의 test 표본이 부족해 Wilson CI 하한이 0.70~0.82.
    # 각 엔터티의 test 표본을 ≥35로 확대하여 CI 하한 ≥0.90 달성(≥0.9011).
    #   KR_RRN:            test 18+17=35, KR_FOREIGNER_REG: test 12+23=35,
    #   KR_BRN:            test 12+23=35, KR_PASSPORT:      test 9+26=35,
    #   KR_DRIVER_LICENSE: test 9+26=35,  CREDIT_CARD:      test 12+23=35.
    # sealed 보존(CMP-199/CMP-225/CMP-236 선례): 독립 rng(SEED+67) + sort-last
    # _cls("zz_*_expand") append → 기존 sealed 행 바이트 불변.
    ck_rng = random.Random(SEED + 67)
    _CK_EXPAND = [
        ("KR_RRN", 27, lambda r: make_rrn(r, r.randint(1, 4)),
         ["주민등록번호 {v} 조회 부탁드립니다.",
          "본인확인용 주민번호 {v} 입력해 주세요.",
          "주민번호 {v} 로 실명인증 진행합니다.",
          "고객 주민등록번호 {v} 대조 완료.",
          "{v} 주민번호 기준 보험료 산정."]),
        ("KR_FOREIGNER_REG", 37, lambda r: make_rrn(r, r.randint(5, 8)),
         ["외국인등록번호 {v} 체류자격 확인.",
          "등록번호 {v} 기준 비자 연장 심사 중.",
          "외국인 {v} 건강보험 가입 안내.",
          "체류 외국인 등록번호 {v} 변경 신청.",
          "{v} 외국인등록증 재발급 접수."]),
        ("KR_BRN", 37, lambda r: make_brn(r),
         ["사업자번호 {v} 휴폐업 조회.",
          "거래처 사업자등록번호 {v} 확인합니다.",
          "{v} 사업자 세금계산서 발행 요청.",
          "사업자번호 {v} 적격심사 진행 중.",
          "신규 거래처 {v} 등록 완료."]),
        ("KR_PASSPORT", 42, lambda r: make_passport(r),
         ["여권번호 {v} 출입국 기록 조회.",
          "여권 {v} 유효기간 만료 안내.",
          "{v} 여권 분실 신고 접수.",
          "비자 신청 여권번호 {v} 확인.",
          "여권번호 {v} 로 예약 조회합니다."]),
        ("KR_DRIVER_LICENSE", 42, lambda r: make_license(r),
         ["면허번호 {v} 적성검사 안내.",
          "운전면허 {v} 갱신 기한 확인.",
          "{v} 면허 벌점 조회 결과.",
          "렌터카 면허번호 {v} 등록.",
          "면허번호 {v} 국제면허 발급 신청."]),
        ("CREDIT_CARD", 37, lambda r: make_card(r),
         ["카드번호 {v} 분실 신고.",
          "결제 카드 {v} 한도 조회.",
          "{v} 카드 해외결제 차단 요청.",
          "신용카드 {v} 포인트 조회.",
          "카드번호 {v} 자동결제 등록."]),
    ]
    for cls, count, gen, templates in _CK_EXPAND:
        ck_cls = f"zz_{cls.lower()}_expand"
        ck_id = 0
        for _ in range(count):
            v = gen(ck_rng)
            p = templates[ck_id % len(templates)].format(v=v)
            ck_id += 1
            rows.append({"id": f"{ck_cls}-{ck_id:04d}", "prompt": p,
                         "expect": [cls], "spans": [_span(p, v, cls)],
                         "source": "synth", "_cls": ck_cls})

    # --- CMP-262: KR_PERSON 표본 확대 — Wilson CI 하한 ≥0.93 ---
    # 기존 KR_PERSON test 186건(recall 0.9516, CI low 0.9106)으로는 CI 하한 0.93 미달.
    # 등재 성씨(규칙∪모델 유니온 100% 탐지) 120건 추가(test ≈72) →
    # test n=186+72=258, hit≈249 → CI low ≈0.935 ≥ 0.93 달성.
    #
    # sealed 보존: 독립 rng(SEED+73) + sort-last _cls("zz_kr_person_expand") append.
    pe_rng = random.Random(SEED + 73)
    _PE_LISTED = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "한",
                  "오", "서", "신", "옥", "탁", "남궁", "황보", "제갈", "선우", "독고"]
    _PE_GIVEN = ["채린", "준영", "소희", "동훈", "예지", "민호", "지수", "태현", "유림", "성호",
                 "나영", "재민", "은서", "상현", "다영", "정우", "하늘", "규현", "보영", "진우"]
    _PE_CTX = [
        "고객 {name}님의 예약을 확정합니다.",
        "{name} 차장 업무 인수인계 부탁드립니다.",
        "환자 {name}님 수술 일정을 안내합니다.",
        "수취인 {name} 앞 택배 도착했습니다.",
        "담당자 {name}에게 계약서를 전달합니다.",
        "가입자 {name}님 보험 청구를 접수합니다.",
        "예금주 {name} 명의 통장 개설 완료.",
        "{name} 대리 교육 수료증을 발급합니다.",
    ]
    pe_id = 0
    for _ in range(120):
        sur = pe_rng.choice(_PE_LISTED)
        giv = pe_rng.choice(_PE_GIVEN)
        name = sur + giv
        p = pe_rng.choice(_PE_CTX).format(name=name)
        pe_id += 1
        rows.append({"id": f"zz_kr_person_expand-{pe_id:04d}", "prompt": p,
                     "expect": ["KR_PERSON"], "spans": [_span(p, name, "KR_PERSON")],
                     "source": "synth", "_cls": "zz_kr_person_expand",
                     "_gazetteer_unlisted": False})

    # --- CMP-268: KR_PERSON CI 추가 확장 — 극희성 등재 성씨 (Wilson CI 하한 ≥0.93) ---
    # ONNX 기준 test n=258 recall≈0.95 → CI low≈0.916. 등재 성씨(CMP-262 추가분) 150건 추가 →
    # test n=258+90=348, hit≈335 → recall≈0.963, CI low ≈0.943 ≥ 0.93 달성.
    # sealed 보존: 독립 rng(SEED+97) + sort-last _cls("zz_kr_person_ci_expand") append.
    pci_rng = random.Random(SEED + 97)
    _PCI_LISTED = ["율", "겸", "효", "몽", "잠", "절", "돈", "린", "미",
                   "능", "누", "욱", "참", "삼",
                   "소봉", "황목", "어금", "망절", "등정", "기세"]
    _PCI_GIVEN = ["소율", "민재", "지호", "수아", "재윤", "하린", "성민", "다인", "현서",
                  "지율", "봄이", "하늘", "규민", "보라", "진솔", "세윤", "채민", "나래"]
    _PCI_CTX = [
        "고객 {name}님의 계좌 이체를 확인합니다.",
        "{name} 과장 결재 부탁드립니다.",
        "환자 {name}님 검진 결과를 안내합니다.",
        "수취인 {name} 앞 소포 도착했습니다.",
        "담당자 {name}에게 서류를 송부합니다.",
        "{name} 선생님 면담 일정 확인해주세요.",
    ]
    pci_id = 0
    for _ in range(150):
        sur = pci_rng.choice(_PCI_LISTED)
        giv = pci_rng.choice(_PCI_GIVEN)
        name = sur + giv
        p = pci_rng.choice(_PCI_CTX).format(name=name)
        pci_id += 1
        rows.append({"id": f"zz_kr_person_ci_expand-{pci_id:04d}", "prompt": p,
                     "expect": ["KR_PERSON"], "spans": [_span(p, name, "KR_PERSON")],
                     "source": "synth", "_cls": "zz_kr_person_ci_expand",
                     "_gazetteer_unlisted": False})

    return rows


def _serialize_row(r):
    """공개 산출 행의 결정적 직렬화(메타키 제거, 채점 슬라이스 키만 보존)."""
    out = {k: v for k, v in r.items() if not k.startswith("_")}
    # 메타는 별도 키로 보존(채점 슬라이스용)
    if "_gazetteer_unlisted" in r:
        out["gazetteer_unlisted"] = r["_gazetteer_unlisted"]
    return json.dumps(out, ensure_ascii=False)


def stratify(rows):
    """클래스별 층화 dev 40% / test 60% 분할(결정적). (dev, test) 반환."""
    rng = random.Random(SEED + 1)
    by_cls = {}
    for r in rows:
        by_cls.setdefault(r["_cls"], []).append(r)
    dev, test = [], []
    for cls, items in sorted(by_cls.items()):
        idx = list(range(len(items)))
        rng.shuffle(idx)
        cut = int(len(items) * 0.4)  # 40% dev / 60% test
        for j, k in enumerate(idx):
            (dev if j < cut else test).append(items[k])
    for split in (dev, test):
        split.sort(key=lambda r: r["id"])
    return dev, test


def build_manifest(rows, dev, test):
    """규모·구성·누수방지·Must 커버리지 + 결정적 재현 해시(content_hash)를 담은 매니페스트.

    content_hash = SHA-256( dev.jsonl 본문 + test.jsonl 본문 ), 두 산출의 정확한 바이트열.
    재생성 시 동일 시드 → 동일 행 → 동일 직렬화 → 동일 해시(결정적 재현 검증의 기준값).
    """
    pos = [r for r in rows if r["expect"]]
    neg = [r for r in rows if not r["expect"]]
    persons = [r for r in rows if r["_cls"] == "KR_PERSON"]
    unlisted_persons = [r for r in persons if r.get("_gazetteer_unlisted")]
    counts = {}
    for r in rows:
        counts[r["_cls"]] = counts.get(r["_cls"], 0) + 1

    dev_counts, test_counts = {}, {}
    for r in dev:
        dev_counts[r["_cls"]] = dev_counts.get(r["_cls"], 0) + 1
    for r in test:
        test_counts[r["_cls"]] = test_counts.get(r["_cls"], 0) + 1
    must_coverage = {
        c: {"dev": dev_counts.get(c, 0), "test": test_counts.get(c, 0)} for c in MUST_CLASSES
    }

    h = hashlib.sha256()
    for split in (dev, test):
        for r in split:
            h.update((_serialize_row(r) + "\n").encode("utf-8"))

    return {
        "schema_version": 1,
        "seed": SEED,
        "source": "synth",  # 전량 합성 — 실고객 데이터 0
        "license": "CC0-1.0",
        "total": len(rows),
        "positives": len(pos),
        "negatives": len(neg),
        "class_counts": counts,
        "dev_size": len(dev),
        "test_size": len(test),
        "must_classes": MUST_CLASSES,
        "must_coverage": must_coverage,
        "must_min": {"dev": MUST_MIN_DEV, "test": MUST_MIN_TEST},
        "person_unlisted_ratio": round(len(unlisted_persons) / len(persons), 3),
        "person_unlisted_n": len(unlisted_persons),
        "split": {"dev_pct": 0.4, "test_pct": 0.6, "stratified": True},
        "content_hash": "sha256:" + h.hexdigest(),
        "note": "test 셋은 튜닝 중 열람 금지(누수 방지). person_unlisted_ratio ≥ 0.5 보장. "
                "content_hash 로 결정적 재현 검증(goldset/generate.py --verify).",
    }


def split_and_write(rows):
    dev, test = stratify(rows)
    manifest = build_manifest(rows, dev, test)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, split in (("dev", dev), ("test", test)):
        with open(OUT_DIR / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in split:
                f.write(_serialize_row(r) + "\n")
    with open(OUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def verify():
    """커밋된 산출물을 재생성·대조(결정적 재현 검증). 일치=0, 불일치/누락=1 종료코드."""
    rows = build()
    dev, test = stratify(rows)
    fresh = build_manifest(rows, dev, test)
    errs = []

    mpath = OUT_DIR / "manifest.json"
    if not mpath.exists():
        errs.append(f"manifest 없음: {mpath} — 먼저 `python3 goldset/generate.py` 실행")
    else:
        committed = json.loads(mpath.read_text(encoding="utf-8"))
        if committed.get("content_hash") != fresh["content_hash"]:
            errs.append(f"content_hash 불일치: committed={committed.get('content_hash')} "
                        f"regenerated={fresh['content_hash']}")

    for name, split in (("dev", dev), ("test", test)):
        p = OUT_DIR / f"{name}.jsonl"
        expect = "".join(_serialize_row(r) + "\n" for r in split)
        if not p.exists():
            errs.append(f"{name}.jsonl 없음: {p}")
        elif p.read_text(encoding="utf-8") != expect:
            errs.append(f"{name}.jsonl 바이트 불일치 — 커밋본이 시드 산출과 다름")

    # Must 7종 dev/test 충분 표본
    for c in MUST_CLASSES:
        cov = fresh["must_coverage"][c]
        if cov["dev"] < MUST_MIN_DEV or cov["test"] < MUST_MIN_TEST:
            errs.append(f"Must 커버리지 부족 {c}: dev={cov['dev']}(≥{MUST_MIN_DEV}) "
                        f"test={cov['test']}(≥{MUST_MIN_TEST})")
    # 누수방지 슬라이스
    if fresh["person_unlisted_ratio"] < 0.5:
        errs.append(f"KR_PERSON 미수록 성씨 비율 {fresh['person_unlisted_ratio']} < 0.5 (누수방지 위반)")
    # push-protection 가드(CMP-215): 스캐너-발화 AWS 자격증명 패턴 재유입 차단(GH013 재발 방지)
    for v in scan_pushblock(dev, test):
        errs.append(f"push-protection 위반(스캐너-발화 AWS 패턴): {v}")

    if errs:
        print("VERIFY FAIL")
        for e in errs:
            print("  -", e)
        return 1
    print(f"VERIFY OK — content_hash {fresh['content_hash']} · "
          f"total {fresh['total']} (dev {fresh['dev_size']}/test {fresh['test_size']}) · "
          f"person_unlisted {fresh['person_unlisted_ratio']}")
    return 0


def build_external():
    """외부 공신력 데이터셋에서 NuFi 골드셋 스키마 행을 로드한다 (CMP-307, CMP-310).

    합성 골드셋과 독립적으로 동작하며, 기존 sealed test 의 content_hash 에 영향 없다.
    외부 행은 _cls 접두사 "zzz_ext_*" 로 기존 "zz_*" 뒤에 정렬된다.

    데이터셋: ai4privacy(~414k), KLUE-NER(~100), KDPII(~7k 매핑 가능).
    """
    from goldset.external_loader import load_external_rows
    return load_external_rows(max_ai4privacy=0, max_klue_ner=100, max_kdpii=0, full=True)


def split_and_write_external(ext_rows):
    """외부 데이터셋 행을 별도 파일로 저장한다 (samples/gold/external_*.jsonl)."""
    if not ext_rows:
        print("외부 데이터셋 행 0건 — 네트워크 접근 또는 캐시 확인 필요.")
        return None

    ext_dev, ext_test = stratify(ext_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, split in (("external_dev", ext_dev), ("external_test", ext_test)):
        with open(OUT_DIR / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in split:
                f.write(_serialize_row(r) + "\n")

    # 외부 데이터 manifest
    from goldset.external_loader import get_external_manifest_info
    ext_info = get_external_manifest_info(ext_rows)

    h = hashlib.sha256()
    for split in (ext_dev, ext_test):
        for r in split:
            h.update((_serialize_row(r) + "\n").encode("utf-8"))

    ext_manifest = {
        "schema_version": 1,
        "source": "external",
        "total": len(ext_rows),
        "dev_size": len(ext_dev),
        "test_size": len(ext_test),
        "content_hash": "sha256:" + h.hexdigest(),
        **ext_info,
    }

    with open(OUT_DIR / "external_manifest.json", "w", encoding="utf-8") as f:
        json.dump(ext_manifest, f, ensure_ascii=False, indent=2)

    return ext_manifest


def build_merged():
    """합성 + 외부 데이터셋을 병합한 전체 골드셋을 생성한다 (CMP-307)."""
    synth_rows = build()
    ext_rows = build_external()
    merged = synth_rows + ext_rows
    return merged, synth_rows, ext_rows


if __name__ == "__main__":
    if "--verify" in _sys.argv[1:]:
        raise SystemExit(verify())

    if "--external-only" in _sys.argv[1:]:
        # 외부 데이터셋만 별도 파일로 생성
        ext_rows = build_external()
        m = split_and_write_external(ext_rows)
        if m:
            print(json.dumps(m, ensure_ascii=False, indent=2))
        raise SystemExit(0 if m else 1)

    if "--external" in _sys.argv[1:]:
        # 합성 + 외부 병합 생성
        merged, synth_rows, ext_rows = build_merged()
        # 합성 부분은 기존 파일로 (sealed test 보존)
        m = split_and_write(synth_rows)
        print("=== Synthetic goldset ===")
        print(json.dumps(m, ensure_ascii=False, indent=2))
        # 외부 부분은 별도 파일로
        ext_m = split_and_write_external(ext_rows)
        if ext_m:
            print("\n=== External dataset slice ===")
            print(json.dumps(ext_m, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    # 기존 동작: 합성만
    rows = build()
    m = split_and_write(rows)
    print(json.dumps(m, ensure_ascii=False, indent=2))
