"""한국어 인명/지명 NER 탐지기 (SPEC M2 수용기준 2).

정규식이 못 잡는 인명/지명을 보완한다.

백엔드 2종 (런타임에 자동 선택):
  1. transformers/ONNX 백엔드 — `Leo97/KoELECTRA-small-v3-modu-ner` (권장, 프로덕션).
     모델 가중치 다운로드(최초 1회)·onnxruntime 또는 torch 필요.
  2. gazetteer 백엔드 (기본/폴백) — 한국 성씨 사전 + 경칭/직함/문맥 게이팅 + 행정구역 접미사.
     순수 stdlib, 에어갭 동작(NFR1). PoC·CI 검증용으로 항상 동작.

gazetteer 백엔드는 호모그래프 오탐을 줄이기 위해 인명은 경칭/직함/문맥으로 게이팅한다.
프로덕션 한국어 PII recall ≥ 0.9 목표는 transformers/ONNX 백엔드로 달성한다(SPEC KR 목표).
"""
from __future__ import annotations

import re
from typing import Iterator, List, Optional

from .korean_pii import RawSpan
from ._infer_pool import BoundedInference


def _is_hangul(ch: str) -> bool:
    """문자가 한글(가-힣) 범위인지 판정."""
    return "\uAC00" <= ch <= "\uD7A3"


# 한국 성씨 사전: 상위 ~60 + 희귀 단성 ~92 (CMP-235, CMP-262). gazetteer 백엔드용.
_SURNAMES = (
    "김|이|박|최|정|강|조|윤|장|임|한|오|서|신|권|황|안|송|전|홍|유|고|문|양|손|"
    "배|백|허|노|심|하|곽|성|차|주|우|구|민|류|나|진|지|엄|채|원|천|방|공|현|함|"
    "변|염|여|추|도|소|석|선|설|마|길|연|위|표|명|기|반|라|왕|"
    # 희귀 단성 ~78 추가 (CMP-235: 미등재 성씨 FN 해소)
    "탁|옥|음|동|경|사|호|모|봉|갈|좌|어|피|빈|단|견|범|복|승|화|초|옹|"
    "국|감|맹|상|편|제|계|팽|풍|종|용|남|은|빙|온|궁|묵|"
    "담|영|태|내|야|매|근|운|판|평|금|수|비|형|독|등|대|혁|무|색|"
    "뇌|필|두|개|부|환|곡|점|시|섭|루|록|번|저|직|란|돌|열|관|해|"
    # 극희성 단성 ~14 추가 (CMP-262: 미수록 인명 FN 해소, CI 하한 0.93 목표)
    "욱|린|능|절|효|미|겸|돈|몽|삼|율|참|누|잠"
)

# 복합 성씨(2음절 성: 남궁·선우·황보·제갈 등, CMP-235/CMP-262). gazetteer 백엔드용.
# 복합 성씨는 단성보다 앞에서 매칭해야 탐욕적 정규식이 올바르게 동작한다.
_COMPOUND_SURNAMES = (
    "남궁|선우|황보|제갈|독고|사공|서문|동방|"
    "사마|상관|공손|장곡|강전|소시|"
    # 극희성 복합 성씨 추가 (CMP-262: 미수록 인명 FN 해소)
    "소봉|황목|어금|망절|등정|기세|위지|부여"
)

# 인명 게이팅: 뒤따르는 경칭/직함, 또는 앞서는 문맥 명사.
_HONORIFICS = "님|씨|군|양"
_TITLES = ("부장|과장|차장|대리|팀장|사원|대표|이사|사장|회장|부사장|상무|전무|"
           "선생|셰프|교수|박사|원장|의원|판사|검사|변호사|기자|감독|선수|작가|"
           "대리님|기사|간호사|약사|의사|"
           # CMP-353: 문맥 후치 역할어(이름 뒤) — "김예린 환자", "참유진 고객" 등 탐지
           "환자|고객")
_CONTEXT = ("고객|환자|담당자|직원|대표|발신자|발신|수신자|수신|성함|이름|사용자|회원|가입자|"
            "신청자|지원자|보호자|의뢰인|수취인|예금주|명의자|"
            # CMP-353: 문맥 전치 역할어(이름 앞) — "당사자 X", "입사자 X", "변호사 X" 등 탐지
            "당사자|입사자|변호사")

# 인명 후보: (성)(이름 1~2자). 게이팅 방식 3종.
#  - 경칭이 바로 붙은 경우 (님/씨/군/양) — 뒤 조사 허용
#  - 공백 뒤 직함이 오는 경우 — 뒤 조사 허용
#  - 앞에 문맥 명사(고객/환자/담당자 등)가 오는 경우 — 일반 후보
# 복합 성씨(2음절)를 단성(1음절)보다 앞에 놓아 탐욕적 매칭 보장(CMP-235).
_NAME = rf"(?:(?:{_COMPOUND_SURNAMES})|(?:{_SURNAMES}))[가-힣]{{1,2}}"
_PERSON_HONOR_RE = re.compile(rf"(?<![가-힣])(?P<name>{_NAME})(?:{_HONORIFICS})")
_PERSON_TITLE_RE = re.compile(rf"(?<![가-힣])(?P<name>{_NAME})\s(?:{_TITLES})")
# CMP-317: 조사(에게/은/를 등) 부착 인명도 문맥 게이팅으로 검출.
# "담당자 겸소율에게" → "겸소율" 매치. 조사 없이 비-한글 경계도 허용.
_PERSON_JOSA = ("에게서|에게|에서|에는|에도|에만|에|은|는|이|가|을|를|"
                "과|와|의|도|만|께|한테|보다|처럼|같이|까지|부터|마다")
_PERSON_CAND_RE = re.compile(
    rf"(?<![가-힣])(?P<name>{_NAME})(?:(?:{_PERSON_JOSA})(?![가-힣])|(?![가-힣]))")
# CMP-357: 인명 패턴에 매치되지만 실제로는 일반명사인 호모그래프 — 오탐 차단.
# "담당"(담+당)은 성씨 "담" + 1음절 이름으로 보이지만 "in charge of"라는 일반어.
# "담당 변호사"가 _PERSON_TITLE_RE 에 매치되어 가명화 시 surrogate 매핑을 교란.
_PERSON_STOPWORDS = frozenset(
    "담당 대표 수배 배당 형사 비서 수사 담보 독자 독립 "
    "효과 효력 효능 율동 율법 겸직 겸손 겸임 몽상 절대 절약 절차".split()
)
_CONTEXT_RE = re.compile(rf"(?:{_CONTEXT})\s*$")

_PLACE_SUFFIX_RE = re.compile(r"(?<![가-힣])([가-힣]{2,4}(?:특별시|광역시|특별자치시|특별자치도))")

# 한국어 조사(지명 뒤에 붙어 경계를 가리는 어미). 캡처에서 제외하고 경계로만 허용해
# "송도국제도시로"·"코엑스몰에서" 같은 josa-부착 지명을 인식한다.
_JOSA = ("으로|로써|로서|로|에서|에게서|에게|에는|에도|에만|에|은|는|이|가|을|를|"
         "과|와|의|도|만|이나|나|이라|라|이며|며|께서|보다|처럼|같이|까지|부터|마다|밖에")
_JOSA_END = rf"(?:{_JOSA})?(?![가-힣])"

# 행정단위 접미사: 뒤에 한글이 바로 오면 비-지명(사회단체도, 면서도 등)일 가능성이
# 높으므로 엄격한 비-한글 경계를 유지한다. 화이트리스트(SIGUNGU) 등재 항목은 별도
# 패스에서 조사 허용으로 처리한다(CMP-312).
_PLACE_UNIT_RE = re.compile(r"(?<![가-힣])([가-힣]{1,4}(?:시|도|군|구|읍|면|동|리))(?![가-힣])")

# 다토큰 행정 스팬(시 + 구, 구 + 동)을 하나로 결합해 경계 품질을 보존한다(P1 §2.2
# class d: "성남시 분당구" 가 "성남시"+"분당구" 로 조각나던 문제). 단일 스팬으로 배출.
# CMP-354: 구+동("강남구 역삼동") 결합도 지원한다.
_METRO_DISTRICT_RE = re.compile(
    rf"(?<![가-힣])([가-힣]{{2,4}}(?:시)\s+[가-힣]{{2,4}}(?:구)){_JOSA_END}"
    rf"|(?<![가-힣])([가-힣]{{2,4}}(?:구)\s+[가-힣]{{2,4}}(?:동)){_JOSA_END}")

# --- 도로명주소 (CMP-221 P2 task 1) -----------------------------------------
# <도로명: …대로|로|길> + 건물번호(숫자[-숫자], 번지/번길 허용). 건물번호를 필수로
# 요구해 "…로 변경"·"참고로" 등 조사/부사 오탐을 차단(정밀도 방어). 예:
#   "테헤란로 152", "판교로 235번길 4", "세종대로 110", "불정로 6번지".
_ROAD_ADDR_RE = re.compile(
    r"(?<![가-힣])([가-힣]{2,10}(?:대로|로|길)\s?\d{1,4}(?:번길)?(?:\s?\d{1,4})?(?:-\d{1,4})?(?:번지)?)")
# …로/대로 로 끝나는 흔한 부사·일반명사(도로명이 아님). 도로명 후보의 "이름"부(번호
# 앞 …로/대로/길)가 이 목록에 정확히 있으면 도로명주소로 보지 않는다(정밀도 방어).
# 접두 2자 미만(주로·서로·바로 등)은 규칙 자체가 매치하지 않아 제외 불필요.
_ROAD_STOPWORDS = frozenset(
    "참고로 별도로 실제로 정말로 대체로 억지로 함부로 저절로 무작위로 임의로 "
    "그대로 이대로 저대로 마음대로 뜻대로 멋대로 제멋대로 되는대로 순서대로 예정대로 "
    "계획대로 원래대로 사실대로 기대로 방법대로 규정대로 "
    "온라인으로 오프라인으로 자동으로 수동으로 상대로 절대로 "
    "도로 통로 경로 진로 회로 미로 활주로 선로 항로 수로 퇴로".split())

# --- 상세주소 (CMP-221 P2 task 2) -------------------------------------------
# 동/호 (101동 203호), 층/호, 지하층. 동+호를 함께 요구해 "제3호"·"3층" 단독
# 오탐을 억제(정밀도 우선). 예: "101동 203호", "3층 402호", "지하 1층".
_DETAIL_ADDR_RE = re.compile(
    r"(?<![\d가-힣])("
    r"\d{1,4}동\s?(?:지하\s?)?\d{1,4}호"           # 101동 203호
    r"|(?:지하\s?)?\d{1,3}층\s?\d{1,4}호"          # 3층 402호 / 지하 1층 12호
    rf")(?:{_JOSA})?(?![\d가-힣])")

# --- 어휘밖 고유지명: 랜드마크/개발지구 접미사 (CMP-221 P2, P1 class c 커버) ----
# 프로덕션 FN(0.79→0.90+ 갭)은 100% "어휘밖 고유지명"(P1 §2/§3): 국제도시·테크노밸리·
# 몰·플라자·시티·호수공원 등 규칙적 접미사를 가진 복합 지명. 접두(한글 2+)를 요구하고
# 일반명사 복합어(쇼핑몰·고객센터 등)는 _LANDMARK_STOPWORDS 로 차단해 정밀도를 지킨다.
_LANDMARK_SUFFIX = ("국제도시|신도시|테크노밸리|디자인플라자|호수공원|월드컵경기장|"
                    "종합운동장|엑스포|밸리|플라자|스퀘어|시티|타워|파크|월드|랜드|"
                    "센터|광장|공원|지구|몰|"
                    # CMP-312: 외부 데이터셋 FN 분석으로 추가된 지명 접미사
                    # "역"은 제외 — "연구용역", "역시" 등 일반명사 FP 과다.
                    "해수욕장|산업단지|산단|공단|약수터|수변길|항구|항|"
                    "터미널|버스터미널|고개|마을")
# CMP-312: 접두 + 선택적 공백 + 접미사 — "송지호 해수욕장"·"무창포해수욕장" 모두 매치.
_LANDMARK_RE = re.compile(
    rf"(?<![가-힣])([가-힣]{{2,8}}\s?(?:{_LANDMARK_SUFFIX})){_JOSA_END}")
# CMP-354: 한글 지명 + 영문 랜드마크/빌딩명 — "여의도 IFC", "판교 알파돔타워" 등
# 알려진 영문 빌딩/시설명. 한글 2-4자 지명 + 공백 + 영문 약칭(2-10자).
_KR_EN_LANDMARKS = frozenset(
    "IFC COEX ASEM KTX SRT DDP DMC LCT BIFC".split())
_KR_EN_LANDMARK_RE = re.compile(
    r"(?<![가-힣])([가-힣]{2,4}\s+(?:" +
    "|".join(re.escape(l) for l in sorted(_KR_EN_LANDMARKS, key=len, reverse=True)) +
    r"))(?![A-Za-z])" + _JOSA_END)
# 위 접미사를 갖지만 지명이 아닌 일반명사 복합어(호모그래프) — 오탐 차단.
_LANDMARK_STOPWORDS = frozenset(
    "쇼핑몰 온라인몰 아울렛몰 오픈마켓몰 종합몰 스마트시티 데이터센터 고객센터 "
    "콜센터 물류센터 서비스센터 연구센터 교육센터 의료센터 관리센터 운영센터 "
    "상담센터 지원센터 놀이공원 근린공원 도시공원 테마파크 워터파크 어린이공원 "
    "관제타워 급수타워 통신타워 컨트롤타워 전망타워 시계탑 "
    # CMP-312: 외부 데이터셋 FP 패턴 — 일반 시설·정책명 (지명 아님)
    "행정복지센터 주민자치센터 통합지원센터 마을지원센터 재생지원센터 보건센터 "
    "종합센터 복합센터 문화센터 체육센터 자원봉사센터 정신건강센터 평생학습센터 "
    "혁신도시 행정수도 신활력도시 도시재생 농어촌마을 "
    # CMP-312: 추가 일반 시설·정책명 — 산업단지/시장/항 복합어 오탐 차단
    "공동체통합지원센터 사회통합센터 취업지원센터 "
    "시민행동 어드벤처월드 쥬라지월드 밥상머리 "
    "거점지구 선거구 특별지구 산업지구 지식산업센터 "
    "공항 항공 출항 입항 "
    # CMP-312: 역/터미널/마을/고개/항 접미사 — 일반명사 오탐 차단
    "면역 발역 검역 방역 반역 역할 위역 변역 번역 통역 역사 "
    "단말기터미널 버스터미널 "
    "마을하수도 마을버스 마을공동체 "
    # CMP-312: 추가 FP 차단 — 됐으면/먹거리/아동 등 비지명 복합어
    "됐으면 되면마을 건의사항 "
    "고개숙여 가마고개".split())

# 전국 시군구 사전(28 → ~230). stdlib·에어갭. 접미사 규칙 매치를 화이트리스트로
# 승격(conf 0.65→0.8)하고 어휘 커버리지를 확장한다. 접미사(시/군/구) 포함 정식명으로
# 저장해 동음이의(중구·동해 등 무접미 형태) 오탐을 원천 차단한다.
_SI = ("수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 "
       "시흥 군포 의왕 하남 용인 파주 이천 안성 김포 화성 광주 양주 포천 여주 "
       "춘천 원주 강릉 동해 태백 속초 삼척 청주 충주 제천 천안 공주 보령 아산 서산 "
       "논산 계룡 당진 전주 군산 익산 정읍 남원 김제 목포 여수 순천 나주 광양 포항 "
       "경주 김천 안동 구미 영주 영천 상주 문경 경산 창원 진주 통영 사천 김해 밀양 "
       "거제 양산 제주 서귀포")
_GUN = ("연천 가평 양평 홍천 횡성 영월 평창 정선 철원 화천 양구 인제 고성 양양 보은 "
        "옥천 영동 증평 진천 괴산 음성 단양 금산 부여 서천 청양 홍성 예산 태안 완주 "
        "진안 무주 장수 임실 순창 고창 부안 담양 곡성 구례 고흥 보성 화순 장흥 강진 "
        "해남 영암 무안 함평 영광 장성 완도 진도 신안 의성 청송 영양 영덕 청도 고령 "
        "성주 칠곡 예천 봉화 울진 울릉 군위 의령 함안 창녕 남해 하동 산청 함양 거창 "
        "합천 강화 옹진 울주 달성 기장")
# 광역시·특별시 자치구(중구·동구 등 방위 구는 정식명 그대로 화이트리스트).
_GU = ("종로 중 용산 성동 광진 동대문 중랑 성북 강북 도봉 노원 은평 서대문 마포 양천 "
       "강서 구로 금천 영등포 동작 관악 서초 강남 송파 강동 서 동 남 북 영도 부산진 "
       "동래 해운대 사하 금정 연제 수영 사상 미추홀 연수 남동 부평 계양 광산 유성 "
       "대덕 수성 달서")
# CMP-312: 세종특별자치시("세종시")를 _SI 에 없지만 SIGUNGU 에 추가.
_SIGUNGU = (frozenset(f"{s}시" for s in _SI.split())
            | frozenset(f"{g}군" for g in _GUN.split())
            | frozenset(f"{d}구" for d in _GU.split())
            | {"세종시"})

# CMP-312: _SI + _GUN bare 이름을 전수 등재해 외부 데이터셋 FN 을 최소화한다.
# 광역시/도 약칭, 국가명, 역사·문화 지명도 함께 등재.
_KNOWN_PLACES = (
    # 광역시·도·특별자치
    set("서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 "
        "경북 경남 제주".split())
    # _SI + _GUN 전수(bare name) — 시/군 접미사 없이 단독으로 쓰이는 케이스 커버
    | set(_SI.split())
    | set(_GUN.split())
    # 자치구 중 3음절 이상(동음이의 위험 낮음)
    | {g for g in _GU.split() if len(g) >= 3}
    # 잘 알려진 2음절 자치구 (일반명사 위험 낮음)
    | set("강남 강북 강서 강동 송파 마포 종로 영등포 관악 서초 노원 "
          "부평 수영 동래 사하 동작 금천 광진 도봉 용산".split())
    # 추가: 별도 지명 (읍, 역세권, 알려진 지역)
    | set("오송 송도 송악 대덕 독도 한반도 서해 동해 남해".split())
    # 국가명/도시명 — 외부 데이터셋 FN 해소
    | set("대한민국 한국 북한 미국 일본 중국 영국 프랑스 독일 호주 캐나다 뉴질랜드 "
          "러시아 필리핀 말레이시아 싱가포르 태국 베트남 인도네시아 대만 몽골 "
          "홍콩 뉴욕 하와이 상하이 스페인 이탈리아 충청 유럽 아시아 덴마크 "
          "우한 방콕 캄보디아 터키 이란 이라크 멕시코 브라질 아르헨티나".split())
    # 역사·문화 지명
    | set("백제 가야 신라 고구려 동아시아 조선".split())
    # CMP-354: 복합 지명(브랜드+지역) — 단일 스팬으로 탐지해야 하는 랜드마크
    | {"스타필드 하남", "스타필드 고양", "스타필드 수원", "스타필드 안성",
       "롯데몰 수지", "롯데몰 은평", "롯데몰 김포",
       "현대백화점 판교", "현대백화점 목동",
       "이케아 고양", "이케아 광명", "이케아 기흥", "이케아 동부산",
       "코스트코 양재", "코스트코 하남", "코스트코 공세"}
)
# CMP-312: 동음이의 위험이 매우 높은 bare 지명 — 조사 또는 비-한글 경계 필수.
# 예산=budget, 고려=consider, 인도=guidance, 경기=game/match, 광주=広州(일반어)
# 도명 약칭(경기/충남 등)은 "경기도민"·"충남발전" 등 비-지명 복합어에서 다빈도.
_KNOWN_AMBIGUOUS = frozenset(
    "경기 세종 강원 충남 충북 전남 전북 경남 경북 "
    "예산 고려 인도 광주 보은 음성 영동 완주 조선 "
    "고성 정선 가평 양평 화천 양구 봉화 "
    # CMP-312: FP 분석 추가 — 강화=strengthen, 달성=achieve, 부여=grant, 고령=old age
    "강화 달성 부여 고령".split()
)

# 행정 접미사를 가진 비(非)지명 호모그래프(오탐 억제). 운영자가 확장 가능.
# (CMP-221 P2 task 4) P1 §2.2 (d)경계 케이스에서 관찰된 일반명사와 겹치는 지명형
# 접미(도/시/구/동 등)를 보강.
_PLACE_STOPWORDS = set(
    "복잡도 정확도 만족도 난이도 신뢰도 자유도 밀도 빈도 강도 농도 온도 속도 각도 "
    "제도 태도 정도 용도 척도 한도 빈도 회의시 도구 연구 요구 지구 인구 가구 기구 "
    "욕구 무시 즉시 동시 임시 항시 일시 운동 활동 행동 작동 자동 수동 이동 부동 "
    "처리 연동 관리 정리 거리 수리 분리 원리 권리 유리 협동 공동 노동 변동 진동 감동 "
    "출동 은행 부서 본부 지사 지부 "
    # 겹치는 일반명사 보강: …도(度/道 아님)·…시(時)·…구(句/球)·…동(動) 등
    "완성도 참여도 몰입도 기여도 선호도 인지도 성숙도 충성도 재현도 해상도 채도 "
    "명도 감도 습도 순도 광도 조도 배송시 결제시 가입시 신청시 시작시 종료시 "
    "발생시 접속시 주문시 어구 문구 단구 야구 축구 농구 탁구 배구 정구 "
    "충동 격동 파동 요동 미동 고동 박동 태동 준동 약동 "
    # …리(里 아님) 일반명사 — 里 접미가 흔한 외래어/합성어를 오탐하던 케이스 보강.
    "메모리 라이브러리 상태관리 카테고리 스토리 히스토리 갤러리 배터리 다이어리 "
    "쿼리 캘린더리 셀러리 로터리 프린터리 딜리버리 리커버리 팩토리 디렉터리 "
    # CMP-312: 외부 한국어 데이터셋 벤치마크에서 관찰된 FP 패턴 보강.
    # …시(~하면/때)·…도(역시/또한)·…면(~하면)·…리(처리) 등 문법접미 오탐.
    "따르면 앞으로도 반드시 일자리 비대면 올해도 년도 당시 다시 우리 보면 매년도 "
    "연간도 그러면 하면 되면 바로시 한편도 오면 나면 가면 "
    # CMP-312: 추가 FP 패턴 — …도(역시/또한) / …시(때) / …면(조건) / 일반명사
    "이외에도 다빈도 부분도 활성화에도 하더라도 지원에도 사업에도 이에도 "
    "과정에서도 결과에도 사례에서도 사회에도 필요시 유사시 비상시 긴급시 "
    "도시 표면 정면 전면 후면 측면 지면 서면 화면 장면 "
    # CMP-312: 전체 벤치마크에서 관찰된 고빈도 FP — 행정단위 접미사 겹침
    "총리 역시 국도 반면 것도 살펴보면 널리 시군 시도 "
    "개시 감시 수시 상시 접시 "
    "것이면 측면 국면 양면 평면 곡면 이면 배면 단면 외면 "
    "것도 대표도 성과도 관행도 등도 사건도 수영장도 "
    "위해서도 위해서라도 다방면 비리 "
    # CMP-312: ~권(圈) 접미사 FP — 지명이 아닌 권역 일반명사
    "수도권 충청권 수도 먹거리 아동 실시 자리 나 도 시".split()
)


# --- 인명 규칙 단독 배출 (CMP-236) ------------------------------------------
# gazetteer 백엔드의 인명 탐지 로직을 모듈 함수로 분리한다. 모델 백엔드(onnx-int8
# 등)와 **인명 채널만** 유니온하기 위해 재사용한다(KR_LOCATION 유니온 CMP-222 P3 와
# 동일 플레이북). 경칭/직함/문맥 게이팅으로 호모그래프 오탐을 억제한다.
def detect_kr_persons(text: str, source: str = "ner:gazetteer") -> Iterator[RawSpan]:
    """텍스트에서 KR_PERSON 후보를 규칙만으로 배출(지명·PII 무관, 순수 stdlib).

    경칭/직함/문맥 게이팅 3종으로 호모그래프 오탐을 억제한다.
    ``source`` 로 배출원을 구분(gazetteer 단독 vs 모델∪규칙 유니온).
    """
    seen: set[tuple[int, int]] = set()

    def emit_person(start, end, name):
        if (start, end) in seen:
            return None
        if name in _PERSON_STOPWORDS:
            return None
        seen.add((start, end))
        return RawSpan("KR_PERSON", name, start, end, 0.75, source=source)

    for rx in (_PERSON_HONOR_RE, _PERSON_TITLE_RE):
        for m in rx.finditer(text):
            span = emit_person(m.start("name"), m.end("name"), m.group("name"))
            if span:
                yield span
    for m in _PERSON_CAND_RE.finditer(text):
        if not _CONTEXT_RE.search(text[max(0, m.start() - 8):m.start()]):
            continue
        span = emit_person(m.start("name"), m.end("name"), m.group("name"))
        if span:
            yield span


# --- 지명(주소) 규칙 단독 배출 (CMP-222 P3) ---------------------------------
# 아래 규칙(도로명·상세주소·랜드마크·시군구·광역·결합 행정 스팬)은 gazetteer
# 백엔드 안에서만 쓰이던 것을 모듈 함수로 분리한다. 모델 백엔드(onnx-int8 등)와
# **주소 채널만** 유니온하기 위해 재사용한다(다른 PII·인명 채널은 건드리지 않음).
# 겹치는 규칙은 우선순위(더 길고 구체적인 스팬 우선)로 하나만 배출한다.
def detect_kr_locations(text: str, source: str = "ner:gazetteer") -> Iterator[RawSpan]:
    """텍스트에서 KR_LOCATION 후보를 규칙만으로 배출(인명·PII 무관, 순수 stdlib).

    P2(CMP-221) 규칙 백엔드 확장을 모델 백엔드와 유니온 가능한 단위로 노출한다.
    ``source`` 로 배출원을 구분(gazetteer 단독 vs 모델∪규칙 유니온)한다.
    """
    loc_spans: list[tuple[int, int]] = []

    def emit_loc(start, end, txt, conf):
        for a, b in loc_spans:
            if start >= a and end <= b:   # 이미 더 넓은 스팬이 커버
                return None
        loc_spans.append((start, end))
        return RawSpan("KR_LOCATION", txt, start, end, conf, source=source)

    # 우선순위 1: 상세주소(동/호) — 가장 구체적
    for m in _DETAIL_ADDR_RE.finditer(text):
        span = emit_loc(m.start(1), m.end(1), m.group(1), 0.8)
        if span:
            yield span
    # 우선순위 2: 도로명주소 (…로/길 + 건물번호). 부사/일반명사 오탐 차단.
    for m in _ROAD_ADDR_RE.finditer(text):
        # 도로명 "이름"부(번호 앞 …로/대로/길)를 뽑아 부사·일반명사(참고로·그대로 등) 차단.
        road_name = re.match(r"[가-힣]+(?:대로|로|길)", m.group(1)).group(0)
        if road_name in _ROAD_STOPWORDS:
            continue
        span = emit_loc(m.start(1), m.end(1), m.group(1), 0.8)
        if span:
            yield span
    # 우선순위 3: 결합 행정 스팬(시+구, 구+동) — 경계 품질(P1 class d, CMP-354)
    for m in _METRO_DISTRICT_RE.finditer(text):
        # 두 대안 중 매치된 그룹을 선택 (시+구 = group 1, 구+동 = group 2)
        matched = m.group(1) or m.group(2)
        start = m.start(1) if m.group(1) else m.start(2)
        end = m.end(1) if m.group(1) else m.end(2)
        span = emit_loc(start, end, matched, 0.85)
        if span:
            yield span
    # 지명: 광역 접미사(특별시/광역시 등)
    for m in _PLACE_SUFFIX_RE.finditer(text):
        span = emit_loc(m.start(1), m.end(1), m.group(1), 0.85)
        if span:
            yield span
    # 지명: 어휘밖 고유지명(랜드마크/개발지구 접미사) — 호모그래프 차단
    for m in _LANDMARK_RE.finditer(text):
        if m.group(1) in _LANDMARK_STOPWORDS:
            continue
        span = emit_loc(m.start(1), m.end(1), m.group(1), 0.7)
        if span:
            yield span
    # CMP-354: 한글 지명 + 영문 랜드마크("여의도 IFC", "삼성 COEX" 등)
    for m in _KR_EN_LANDMARK_RE.finditer(text):
        span = emit_loc(m.start(1), m.end(1), m.group(1), 0.75)
        if span:
            yield span
    # 지명: 행정단위 접미사 (호모그래프 제외). 시군구 사전 등재 시 conf 승격.
    for m in _PLACE_UNIT_RE.finditer(text):
        if m.group(1) in _PLACE_STOPWORDS:
            continue
        conf = 0.8 if m.group(1) in _SIGUNGU else 0.65
        span = emit_loc(m.start(1), m.end(1), m.group(1), conf)
        if span:
            yield span
    # CMP-312: SIGUNGU 화이트리스트 항목은 조사 부착형도 매치(금산군을, 음성읍민 등).
    # _PLACE_UNIT_RE 의 (?![가-힣]) 경계가 차단하는 josa 케이스를 보완한다.
    for sigungu in _SIGUNGU:
        start = 0
        while True:
            idx = text.find(sigungu, start)
            if idx < 0:
                break
            end_idx = idx + len(sigungu)
            # 앞-경계: 한글 앞 글자가 없어야 함
            before_ok = idx == 0 or not _is_hangul(text[idx - 1])
            if before_ok:
                span = emit_loc(idx, end_idx, sigungu, 0.8)
                if span:
                    yield span
            start = end_idx
    # 지명: 알려진 광역/축약 지명 (CMP-312: 한글 경계 검사 추가, FP 억제)
    for place in _KNOWN_PLACES:
        start = 0
        while True:
            idx = text.find(place, start)
            if idx < 0:
                break
            end_idx = idx + len(place)
            # 앞-경계: 한글이 바로 앞에 있으면 다른 단어의 일부 → 스킵
            before_ok = idx == 0 or not _is_hangul(text[idx - 1])
            # 뒤-경계: 동음이의 위험 높은 _KNOWN_AMBIGUOUS 만 엄격(조사/비한글).
            # 나머지는 한글 복합어 허용 (대전시장·부산회의 등 지명+명사 자연스러움).
            if place in _KNOWN_AMBIGUOUS:
                after_ok = end_idx >= len(text) or not _is_hangul(text[end_idx])
                if not after_ok:
                    after_ok = bool(re.match(_JOSA, text[end_idx:]))
            else:
                after_ok = True
            if before_ok and after_ok:
                conf = 0.6 if place in _KNOWN_AMBIGUOUS else 0.7
                span = emit_loc(idx, end_idx, place, conf)
                if span:
                    yield span
            start = end_idx


class _GazetteerBackend:
    name = "gazetteer"

    def detect(self, text: str) -> Iterator[RawSpan]:
        # 인명: 규칙 단위로 분리(CMP-236, detect_kr_persons) — 모델 백엔드와 유니온 재사용.
        yield from detect_kr_persons(text, source="ner:gazetteer")
        # 지명(주소)은 규칙 단위로 분리(CMP-222 P3, detect_kr_locations) — 모델 백엔드와
        # 유니온 재사용. 우선순위(구체적 스팬 우선)·호모그래프 차단은 함수 내부에 보존.
        yield from detect_kr_locations(text, source="ner:gazetteer")


class _PipelineBackend:
    """transformers token-classification 파이프라인 공통 채점 로직.

    하위 클래스가 `self._pipe`(HF token-classification 파이프라인)와
    `name`/`source` 만 구성하면 detect() 가 공유된다. FP32(torch)·INT8(ONNX) 동일.
    """

    name = "pipeline"
    source = "ner:koelectra"
    _LABEL_MAP = {"PS": "KR_PERSON", "PER": "KR_PERSON", "LC": "KR_LOCATION", "LOC": "KR_LOCATION"}
    # CMP-127: 부하 하 코어 과구독 방지용 공유 bounded 추론 풀(백엔드별 1개).
    # 모델 백엔드 __init__ 에서 주입. gazetteer 는 None(순수 stdlib, 풀 불필요).
    _pool: Optional[BoundedInference] = None

    def detect(self, text: str) -> Iterator[RawSpan]:
        # 추론(self._pipe)만 W-bounded 풀에서 실행 → 동시 추론 수를 코어수에
        # 수렴시켜 과구독을 제거(CMP-127). 결과를 풀 안에서 materialize 한 뒤 yield.
        if self._pool is not None:
            ents = self._pool.run(lambda: list(self._pipe(text)))
        else:
            ents = self._pipe(text)
        for ent in ents:
            grp = str(ent.get("entity_group", "")).upper()
            mapped = next((v for k, v in self._LABEL_MAP.items() if grp.startswith(k)), None)
            if not mapped:
                continue
            yield RawSpan(mapped, ent["word"], int(ent["start"]), int(ent["end"]),
                          float(ent["score"]), source=self.source)


class _TransformersBackend(_PipelineBackend):
    """transformers token-classification 파이프라인 (KoELECTRA FP32, torch)."""

    name = "transformers"
    source = "ner:koelectra"

    def __init__(self, model_id: Optional[str] = None):
        import os
        from transformers import pipeline  # type: ignore
        # CMP-127: 코어 전용화 — torch intra-op 스레드를 K 로 캡(프로세스 전역).
        # 동시 추론은 BoundedInference(W) 가 제한 → W×K ≈ cores.
        self._pool = BoundedInference()
        try:
            import torch  # type: ignore
            torch.set_num_threads(self._pool.intra_op)
        except Exception:
            pass
        # CMP-123 격상: 명시 model_id > env M5_NER_MODEL_ID > 기본 small.
        model_id = model_id or os.environ.get(
            "M5_NER_MODEL_ID", "Leo97/KoELECTRA-small-v3-modu-ner")
        self._pipe = pipeline("token-classification", model=model_id,
                              aggregation_strategy="simple")


class _OnnxInt8Backend(_PipelineBackend):
    """ONNX 동적 INT8 런타임 백엔드 (optimum onnxruntime).

    `scripts/export_onnx_int8.py` 가 산출한 INT8 ONNX 디렉터리를 로드한다.
    경로는 `model_id`(디렉터리) 또는 env `M5_ONNX_DIR/int8` 로 지정.
    """

    name = "onnx-int8"
    source = "ner:koelectra-onnx-int8"

    def __init__(self, model_id: Optional[str] = None):
        import glob
        import os
        from optimum.onnxruntime import ORTModelForTokenClassification  # type: ignore
        from transformers import AutoConfig, AutoTokenizer, pipeline  # type: ignore

        model_dir = model_id or os.environ.get("M5_ONNX_DIR") \
            or os.path.expanduser("~/.cache/m5_onnx_int8")
        # config.json 유무로 견고하게 해석(디렉터리명 의존 금지). 부모를 줬는데
        # int8/ 하위에 모델이 있으면 내려간다. (parent 명이 ...int8 로 끝나
        # endswith 체크가 오판하던 버그 수정 — CMP-127.)
        if not os.path.isfile(os.path.join(model_dir, "config.json")):
            cand = os.path.join(model_dir, "int8")
            if os.path.isfile(os.path.join(cand, "config.json")):
                model_dir = cand
        if not os.path.isfile(os.path.join(model_dir, "config.json")):
            raise FileNotFoundError(
                f"INT8 ONNX 모델 없음: {model_dir} — 먼저 `python3 scripts/export_onnx_int8.py`")
        # 비표준 파일명(model_quantized.onnx) 자동 탐지. file_name 을 명시하지 않으면
        # optimum 이 표준 model.onnx 를 못 찾아 베이스 모델을 즉석 재export(FP32) 하므로
        # 측정 대상이 INT8 가 아니게 된다 — 반드시 양자화 파일을 지정한다(CMP-127).
        onnx_files = [os.path.basename(p) for p in glob.glob(os.path.join(model_dir, "*.onnx"))]
        file_name = next((f for f in ("model_quantized.onnx", "model.onnx") if f in onnx_files),
                         onnx_files[0] if onnx_files else None)
        # CMP-127: 코어 전용화 — onnxruntime intra-op 스레드를 K 로 캡.
        # 동시 추론은 BoundedInference(W) 가 제한 → W×K ≈ cores(과구독 제거).
        self._pool = BoundedInference()
        sess_opts = None
        try:
            import onnxruntime as ort  # type: ignore
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = self._pool.intra_op
            sess_opts.inter_op_num_threads = 1
        except Exception:
            sess_opts = None
        # config 명시 → optimum 의 library 자동추론 실패를 회피(optimum 4.5x).
        from_kwargs = {"config": AutoConfig.from_pretrained(model_dir)}
        if file_name:
            from_kwargs["file_name"] = file_name
        if sess_opts is not None:
            from_kwargs["session_options"] = sess_opts
        try:
            model = ORTModelForTokenClassification.from_pretrained(model_dir, **from_kwargs)
        except TypeError:
            # 구버전 optimum: 일부 kwarg 미지원 → config/file_name 만으로 폴백.
            model = ORTModelForTokenClassification.from_pretrained(
                model_dir, config=from_kwargs["config"], **({"file_name": file_name} if file_name else {}))
        tok = AutoTokenizer.from_pretrained(model_dir)
        self._pipe = pipeline("token-classification", model=model, tokenizer=tok,
                              aggregation_strategy="simple")


class _MultilingualTransformersBackend(_PipelineBackend):
    """다국어 NER 백엔드 — 영어/다국어 텍스트용 (CMP-309).

    dslim/bert-base-NER (또는 동급 다국어 모델)을 사용한다.
    라벨 맵은 CoNLL 표준(PER/LOC/ORG/MISC) → 내부 타입(PERSON/LOCATION).
    """

    name = "multilingual"
    source = "ner:multilingual"
    _LABEL_MAP = {"PER": "PERSON", "LOC": "LOCATION", "ORG": "ORGANIZATION"}

    def __init__(self, model_id: Optional[str] = None):
        import os
        from transformers import pipeline  # type: ignore
        self._pool = BoundedInference()
        try:
            import torch  # type: ignore
            torch.set_num_threads(self._pool.intra_op)
        except Exception:
            pass
        model_id = model_id or os.environ.get(
            "M5_MULTILINGUAL_NER_MODEL_ID", "dslim/bert-base-NER")
        self._pipe = pipeline("token-classification", model=model_id,
                              aggregation_strategy="simple")


class MultilingualNerDetector:
    """영어/다국어 텍스트용 NER 탐지기 (CMP-309).

    KoreanNerDetector 와 동일 인터페이스(detect(text) → Iterator[RawSpan]).
    백엔드 선택: transformers(dslim/bert-base-NER) 또는 disabled.
    """

    def __init__(self, backend: str = "auto", model_id: Optional[str] = None):
        self.backend = self._build_backend(backend, model_id)

    @staticmethod
    def _build_backend(backend: str, model_id: Optional[str]):
        if backend in ("auto", "transformers", "multilingual"):
            try:
                return _MultilingualTransformersBackend(model_id=model_id)
            except Exception:
                if backend in ("transformers", "multilingual"):
                    raise
        return None

    @property
    def backend_name(self) -> str:
        if self.backend is None:
            return "disabled"
        return getattr(self.backend, "name", "unknown")

    @property
    def pool_config(self):
        pool = getattr(self.backend, "_pool", None)
        return pool.config if pool is not None else None

    def detect(self, text: str) -> Iterator[RawSpan]:
        if self.backend is not None:
            yield from self.backend.detect(text)


class KoreanNerDetector:
    """가능하면 transformers 백엔드, 아니면 gazetteer 폴백.

    ``location_union`` (CMP-222 P3): 주소 채널(KR_LOCATION)에 한해 **모델 백엔드 ∪
    확장 규칙(P2)** 유니온을 활성화한다. 모델 백엔드(transformers/onnx-int8)가 놓치는
    구조적·어휘밖 주소를 규칙으로 회복해 재현율을 끌어올린다. recall(A∪B) ≥ max(A,B)
    가 보장되고(스팬을 더할 뿐 제거하지 않음), 정밀도는 P2 차단목록으로 방어한다.
    다른 PII·인명 채널은 건드리지 않는다.

    ``person_union`` (CMP-236): 인명 채널(KR_PERSON)에 한해 **모델 백엔드 ∪ 규칙
    (경칭/직함/문맥 게이팅)** 유니온을 활성화한다. 모델이 놓치는 등재 성씨 인명을
    규칙으로 회복한다. KR_LOCATION 유니온과 동일 플레이북(스팬 추가 전용, _merge 중복
    제거). gazetteer 백엔드는 이미 규칙을 포함하므로 유니온이 무의미 → no-op.
    """

    def __init__(self, backend: str = "auto", model_id: Optional[str] = None,
                 location_union: bool = False, person_union: bool = False):
        self.backend = self._build_backend(backend, model_id)
        # 규칙은 gazetteer 백엔드에 이미 있으므로 모델 백엔드일 때만 유니온한다.
        self.location_union = bool(location_union) and self.backend_name != "gazetteer"
        self.person_union = bool(person_union) and self.backend_name != "gazetteer"

    @staticmethod
    def _build_backend(backend: str, model_id: Optional[str]):
        if backend == "onnx-int8":
            return _OnnxInt8Backend(model_id=model_id)  # 미가용 시 예외 전파(폴백 금지: 명시 측정용)
        if backend in ("auto", "transformers"):
            try:
                kwargs = {"model_id": model_id} if model_id else {}
                return _TransformersBackend(**kwargs)
            except Exception:
                if backend == "transformers":
                    raise
        return _GazetteerBackend()

    @property
    def backend_name(self) -> str:
        return getattr(self.backend, "name", "unknown")

    @property
    def pool_config(self) -> Optional[dict]:
        """모델 백엔드의 동시성 풀 설정(K/W/cores). gazetteer 는 None."""
        pool = getattr(self.backend, "_pool", None)
        return pool.config if pool is not None else None

    def detect(self, text: str) -> Iterator[RawSpan]:
        yield from self.backend.detect(text)
        # 주소 채널만 규칙 유니온(CMP-222 P3). 겹치는 스팬은 파이프라인 _merge 가
        # 점수·길이 우선으로 하나만 남기되, 어느 백엔드든 잡으면 KR_LOCATION 존재는
        # 보장되므로 클래스 recall(A∪B) ≥ max(A,B). 인명/기타 PII 는 미포함.
        if self.location_union:
            yield from detect_kr_locations(text, source="rule:kr-location")
        # 인명 채널 규칙 유니온(CMP-236). 모델이 놓친 등재 성씨 인명을 규칙
        # (경칭/직함/문맥 게이팅)으로 회복. 위 주소 유니온과 동일 플레이북.
        if self.person_union:
            yield from detect_kr_persons(text, source="rule:kr-person")
