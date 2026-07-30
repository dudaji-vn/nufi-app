# Security Policy

## Supported Versions

| 버전       | 지원 상태 |
| ---------- | --------- |
| 0.4.x      | :white_check_mark: 지원 |
| < 0.4      | :x: 미지원 |

현재 최신 릴리스는 **v0.4.18**입니다.

---

## Reporting a Vulnerability

보안 취약점을 발견하셨다면 아래 방법 중 하나로 신고해 주세요.

1. **이메일**: [security@dudaji.com](mailto:security@dudaji.com) 로 발견 내용을 보내 주세요.
2. **GitHub Private Security Advisory**: 이 저장소의 *Security* 탭 → *Report a vulnerability* 를 통해 비공개 리포트를 작성할 수 있습니다.

신고 시 포함해 주시면 좋은 정보:

- 영향받는 버전 및 구성
- 재현 절차(PoC 코드 포함 시 더 빠르게 대응 가능)
- 예상되는 영향 범위

> **중요**: 취약점이 패치되기 전까지 공개 이슈나 SNS에 공개하지 말아 주세요.

---

## Response Timeline

| 단계               | 목표 시간        |
| ------------------ | --------------- |
| 수신 확인           | 48시간 이내      |
| 심각도 평가·분류     | 5영업일 이내     |
| 패치 릴리스 목표     | 14일 이내        |

심각도에 따라 일정이 앞당겨질 수 있습니다. 진행 상황은 신고자에게 직접 안내합니다.

---

## Out of Scope

다음 항목은 신고 범위에 포함되지 않습니다.

- **의도적 설계 제한**: NuFi의 규칙 기반 탐지·가명화는 설계상 PoC 수준이며, 모든 입력을 완벽히 처리하지 않습니다.
- **PoC 전용 한계**: 프로덕션 배포를 전제하지 않은 기능의 보안 강도 부족(예: 테스트용 시뮬레이션 모드).
- **이미 알려진 한계**: 아래 "Known Limitations" 섹션 또는 README에 명시된 사항.
- **서비스 거부(DoS)**: 로컬 전용 CLI 도구 특성상 네트워크 DoS는 범위 밖입니다.

---

## Known Limitations

현재 알려진 한계는 [`README.md` § 현재 상태와 한계](README.md#현재-상태와-한계-status--limitations) 를 참고하세요. 주요 항목:

- 한국어 인명(KR_PERSON) 재현율은 사전 미수록 희성·복성에서 FN이 발생할 수 있습니다.
- 외부 원문 보존 옵션을 켜면 원문이 디스크에 남습니다(기본 꺼짐).
- 라이브 패킷 캡처는 관리자 권한(root/CAP_NET_RAW)이 필요합니다.

---

## Acknowledgements

책임 있는 공개(responsible disclosure)를 통해 NuFi의 보안 개선에 기여해 주신 분들께 감사드립니다.
