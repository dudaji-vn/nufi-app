# Box acceptance — 2026-09-08T17:01:01 — https://nufi.local:3080

**10/32 checks passed** (22 failures).

## legal (agent agent_LRBK7LMmYz2WrdJLuE8zb, ingested in 0.1 s)
- **자동연장 조항이 있는 계약은 만료 며칠 전까지 통보해야 하나요?** → FAIL (1.9 s)
  - leton
{"name": "file_search", "arguments": {"query": "자동연장 조항 만료 통보 기간"}}
</tool_call>
  - verdict: does not state '60'
  - sources: none
- **NDA의 비밀유지 의무는 계약 종료 후 몇 년간 존속하나요?** → PASS (4.6 s)
  - NDA의 비밀유지 의무는 계약 종료일로부터 3년간 존속합니다. 그러나 영업비밀에 해당하는 정보는 기간 제한 없이 보호될 수 있습니다. 이 내용은 "계약 검토 표준 조항" 문서에서 확인할 수 있습니다.
  - sources: 계약검토_표준조항.txt
- **고위험 조항으로 분류되는 것들은 무엇인가요?** → FAIL (4.0 s)
  - 고위风险条款包括：无限赔偿责任、单方面解除合同、全部知识产权转让以及竞业禁止超过三年的条款。这些条款一旦发现，应立即向法务团队报告。
  - verdict: does not state '손해배상'
  - sources: 계약검토_표준조항.txt
- **직원 퇴직금은 어떻게 계산하나요?** → PASS (14.7 s)
  - 먼저, 계약검토_표준조항.txt 파일을 검색해 보겠습니다.

검색된 파일 "계약검토_표준조항.txt"에는 직원 퇴직금 관련 내용이 포함되어 있지 않습니다. 이 문서는 주로 계약의 자동 연장, 손해배상 한도, 비밀유지 기간, 준거법 및 관할, 고위험 조항 등에 대한 정보를 제공하고 있습니다.

퇴직금 계산 방법과 관련된 내용은 다른 문서에서 찾으실 필요가 있을 수 있습니다. 혹시 특정 회사의 정책이나 근로기준법을 따르는지 궁금하시다면 추가적인 검색을 도와드리겠습니다.
  - sources: none

## hr (agent agent_vlKA62gmhHq1HLNrNSTob, ingested in 0.1 s)
- **배우자 출산 시 휴가는 며칠인가요?** → FAIL (2.4 s)
  - leton
{"name": "file_search", "arguments": {"query": "배우자 출산 휴가 기간"}}
</tool_call>
  - verdict: does not state '10'
  - sources: none
- **재택근무는 주 며칠까지 신청할 수 있나요?** → FAIL (1.5 s)
  - leton
{"name": "file_search", "arguments": {"query": "재택근무 주별 신청 가능 일자"}}
</tool_call>
  - verdict: does not state '2'
  - sources: none
- **병가를 3일 넘게 쓰려면 무엇이 필요한가요?** → PASS (6.1 s)
  - 병가를 3일 넘게 사용하려면 의사 진단서를 제출해야 합니다. 병가 기간 중 최초 30일은 통상임금의 100%, 이후는 70%를 지급받을 수 있습니다.

이 정보는 "취업규칙 발췌 — 휴가 및 근태 (2026-01 시행)" 문서에서 얻었습니다.
  - sources: 취업규칙_휴가.txt
- **해외 출장 항공권은 어느 등급으로 예약하나요?** → PASS (39.1 s)
  - 먼저 취업규칙_휴가.txt 파일을 검색하겠습니다.

검색된 문서에는 항공권 관련 정보가 포함되어 있지 않습니다. 따라서 해외 출장 항공권 등급에 대한 정보를 제공할 수 없습니다. 다른 파일을 검토하거나 추가 정보를 제공해 주시면 도와드리겠습니다. 

文件搜索结果如下：
文件： 취业规则_休假_06206ba0c5944c2381eaaf4ccb2ffcc0.txt
相关性： 0.4122
内容摘录： 
第三条（年假）连续工作一年的员工将获得带薪年假15天。超过第一年的连续工龄每两年增加一天，总假期天数上限为25天。未使用的年假将在会计年度结束时失效。

第四条（婚丧嫁娶假）给予以下假期：本人结婚5天、子女结婚1天、配偶生育10天、父母或配偶去世5天、祖父母去世3天。

第五条（病假）每年最多可享受60天的病假，超过3天需提交医生诊断书。病假期间前30天按正常工资支付，之后按70%支付。

第六条（远程工作）每周可以申请2天远程工作，经团队负责人批准后实施。新入职员工在试用期三个月内不能申请远程工作。

第七条（试用期）新入职员工的试用期为3个月，在试用期内工资为正常工资的90%。

以上内容未提及关于出差机票等级的信息。
  - sources: none

## ga (agent agent_WOKpReDCZeIX5Ovnc4tXe, ingested in 0.2 s)
- **법인카드 1회 사용 한도는 얼마인가요?** → FAIL (4.7 s)
  - leton
{"name": "file_search", "arguments": {"query": "법인카드 1회 사용 한도"}}
</tool_call>
  - verdict: does not state '50'
  - sources: none
- **도서구입비는 연간 얼마까지 지원되나요?** → FAIL (5.5 s)
  - leton
{"name": "file_search", "arguments": {"query": "연간 도서구입비 지원 금액"}}
</tool_call>
  - verdict: does not state '30'
  - sources: none
- **회의실을 예약하고 사용하지 않으면 어떻게 되나요?** → FAIL (1.2 s)
  - leton
{"name": "file_search", "arguments": {"query": "회의실 예약 미사용 시"})
</tool_call>
  - verdict: does not state '취소'
  - sources: none
- **퇴사할 때 노트북은 어디에 반납하나요?** → FAIL (1.4 s)
  - leton
{"name": "file_search", "arguments": {"query": "퇴사할 때 노트북 반납"}}
</tool_call>
  - verdict: answered a question the document does not cover
  - sources: none

## strategy (agent agent_b_S05mvFQkZaG_00Tp3Q2, ingested in 0.0 s)
- **3분기 핵심 목표 세 가지는 무엇인가요?** → FAIL (2.1 s)
  - 
  - verdict: empty answer
  - sources: none
- **분기 예산에서 연구개발 비중은 몇 퍼센트인가요?** → PASS (11.0 s)
  - 분기 예산에서 연구개발 비중은 60%입니다. 

이 정보는 "2026년 3분기 사업계획 요약" 문서에서 찾았습니다. 해당 문서는 전략기획팀이 작성하고, 2026년 6월 28일에 확정되었습니다.
  - sources: 2026_3분기_사업계획.txt
- **가장 큰 리스크와 그 대응책은 무엇인가요?** → PASS (16.8 s)
  - 가장 큰 리스크는 파일럿 부서의 IT 승인 지연입니다. 이 문제에 대응하기 위해 IT 승인이 필요 없는 부서 단위 설치 경로를 우선 제안하고 있습니다.
  - sources: none
- **4분기 채용 계획은 몇 명인가요?** → PASS (6.1 s)
  - 让我使用文件搜索工具来查找相关信息。

根据搜索结果，文件中并未提及第四季度的招聘计划。因此我无法提供具体的数字。

文件内容主要集中在2026年第三季度的业务计划上，包括核心目标、预算分配和关键里程碑等信息。如果您需要了解有关第四季度的信息，建议查阅相关文档或向相关部门咨询。
  - sources: 2026_3분기_사업계획.txt

## finance (agent agent_WGDjjC87sIRVzRYvS3XPe, ingested in 0.1 s)
- **고정자산으로 계상하는 취득가 기준은 얼마인가요?** → FAIL (2.0 s)
  - leton
{"name": "file_search", "arguments": {"query": "고정자산 취득가 기준"}}
</tool_call>
  - verdict: does not state '100'
  - sources: none
- **노트북의 내용연수는 몇 년인가요?** → FAIL (1.0 s)
  - leton
{"name": "file_search", "arguments": {"query": "노트북 내용연수 회계처리"}}
</tool_call>
  - verdict: does not state '4'
  - sources: none
- **중복 지급 의심 건은 어떤 기준으로 분류하나요?** → FAIL (1.0 s)
  - leton
{"name": "file_search", "arguments": {"query": "중복 지급 의심 건 분류 기준"}}
</tool_call>
  - verdict: does not state '30'
  - sources: none
- **임직원 스톡옵션 행사가는 어떻게 정하나요?** → FAIL (1.5 s)
  - leton
{"name": "file_search", "arguments": {"query": "스토크옵션 행사가是如何用韩语回答的？"}}
</tool_call>
  - verdict: answered a question the document does not cover
  - sources: none

## sales (agent agent_07XjKy0SrfaBai46Wme6o, ingested in 0.1 s)
- **팀장이 전결로 승인할 수 있는 할인율은 몇 퍼센트까지인가요?** → FAIL (1.8 s)
  - leton
{"name": "file_search", "arguments": {"query": "팀장이 전결로 승인할 수 있는 최대 할인율"}}
</tool_call>
  - verdict: does not state '10'
  - sources: none
- **파일럿 기간은 기본 몇 주인가요?** → PASS (5.5 s)
  - 파일럿 기간은 기본적으로 8주입니다. 최대 12주까지 연장이 가능합니다.
  - sources: 영업_가격정책.txt
- **견적의 유효기간은 며칠인가요?** → PASS (25.3 s)
  - 견적의 유효기간은 발행일로부터 30일입니다. 이 정보는 "영업_가격정책.txt" 파일에서 확인할 수 있습니다.
  - sources: 영업_가격정책.txt
- **영업사원 인센티브 지급률은 얼마인가요?** → PASS (6.1 s)
  - Tôi đã sử dụng công cụ tìm kiếm file để tìm thông tin về chính sách thưởng cho nhân viên bán hàng nhưng không có thông tin cụ thể về tỷ lệ thưởng trong tài liệu được cung cấp.

영업사원 인센티브 지급률에 대한 정보는 제공된 파일에서 찾을 수 없습니다. 해당 파일은 주로 어플라이언스 판매 정책, 파일럿 조건, 견적 유효기간, RFP 대응 및 경쟁 대응 관련 내용을 다루고 있습니다.
  - sources: 영업_가격정책.txt

## support (agent agent_GyUUYedxSYPmDXxjh3OK3, ingested in 0.1 s)
- **P1 티켓의 1차 응답 목표 시간은 얼마인가요?** → FAIL (2.4 s)
  - 文件搜索未找到直接关于P1票的1次响应目标时间的信息。请提供更具体的查询或检查其他文档。

用于搜索的文件： 고객지원_대응기준.txt
  - verdict: does not state '30'
  - sources: none
- **공유 드라이브가 보이지 않는다는 문의에는 무엇을 먼저 안내하나요?** → FAIL (1.3 s)
  - leton
{"name": "file_search", "arguments": {"query": "공유 드라이브가 보이지 않는다는 문제 해결 방법"}}
</tool_call>
  - verdict: does not state '진단'
  - sources: none
- **응답 목표 시간을 넘기면 어떻게 되나요?** → FAIL (1.2 s)
  - leton
{"name": "file_search", "arguments": {"query": "응답 목표 시간을 넘기면"}}
</tool_call>
  - verdict: does not state '상향'
  - sources: none
- **고객사 환불 규정은 어떻게 되나요?** → FAIL (6.2 s)
  - 문서에는 직접적인 환불 규정이 언급되어 있지 않습니다. 하지만, 일반적인 대응 기준에 따르면, 고객의 문의나 문제 해결은 3영업일 이내에 이루어져야 합니다. 특정 상황에서 문제가 지속될 경우, 우선순위가 높아질 수 있습니다.

만약 환불과 관련된 구체적인 규정이 필요하다면, 다른 문서를 확인하거나 고객 지원팀에게 직접 문의해 주세요.
  - verdict: answered a question the document does not cover
  - sources: 고객지원_대응기준.txt

## engineering (agent agent_95iumGf9Mb85aepJ3hm_Z, ingested in 0.1 s)
- **운영 배포를 하지 않는 시간대는 언제인가요?** → FAIL (2.1 s)
  - leton
{"name": "file_search", "arguments": {"query": "운영 배포를 하지 않는 시간대"}}
</tool_call>
  - verdict: does not state '금요일'
  - sources: none
- **장애 사후분석은 며칠 이내에 작성하나요?** → FAIL (1.0 s)
  - leton
{"name": "file_search", "arguments": {"query": "장애 사후분석 작성 기간"}}
</tool_call>
  - verdict: does not state '5'
  - sources: none
- **도커 이미지 태그 사용 규칙은 무엇인가요?** → FAIL (1.0 s)
  - leton
{"name": "file_search", "arguments": {"query": "도커 이미지 태그 사용 규칙"}}
</tool_call>
  - verdict: does not state '고정'
  - sources: none
- **신입 개발자 온보딩 교육은 몇 주인가요?** → FAIL (1.4 s)
  - 문서에 따르면, 신입 개발자 온보딩 교육은 4주간 이루어집니다.

이 정보는 "개발_운영기준.txt" 파일에서 얻었습니다.
  - verdict: answered a question the document does not cover
  - sources: none
