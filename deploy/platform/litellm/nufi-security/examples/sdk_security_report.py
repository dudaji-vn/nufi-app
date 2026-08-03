"""NuFi Python SDK — 보안 리포트 생성 예시.

디렉터리를 스캔하고 보안 현황 리포트(Markdown)를 생성합니다.
자세한 API 문서: docs/SDK.md

실행:
    python3 examples/sdk_security_report.py
"""
import pathlib
import sys
import tempfile
import os
import shutil

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from nufi import security_report, render_security_markdown, render_security_json

# --- 1. 임시 프로젝트 디렉터리 구성 --------------------------------
project_dir = tempfile.mkdtemp(prefix="nufi_report_demo_")

try:
    # PII 포함 파일
    data_dir = os.path.join(project_dir, "data")
    os.makedirs(data_dir)

    with open(os.path.join(data_dir, "customers.txt"), "w", encoding="utf-8") as f:
        f.write("고객 홍길동 주민번호 900101-1234567\n")
        f.write("이메일: hong@example.com\n")

    with open(os.path.join(data_dir, "contacts.txt"), "w", encoding="utf-8") as f:
        f.write("연락처: 010-9876-5432\n")
        f.write("담당자 김민수\n")

    # 클린 파일
    with open(os.path.join(project_dir, "readme.txt"), "w", encoding="utf-8") as f:
        f.write("This project contains customer data.\n")
        f.write("Handle with care.\n")

    # --- 2. 보안 리포트 생성 ----------------------------------------
    print("[보안 리포트 생성]")
    report = security_report(project_dir)

    print(f"  스캔 파일:      {report.files_scanned}")
    print(f"  발견 있는 파일: {report.files_with_findings}")
    print(f"  총 발견 수:     {report.total_findings}")
    print(f"  위험 수준:      {report.risk_level}")
    print()

    # 심각도별 분포
    if report.findings_by_severity:
        print("  심각도별 분포:")
        for severity, count in report.findings_by_severity.items():
            print(f"    {severity}: {count}건")
        print()

    # 상위 엔티티 유형
    if report.top_entity_types:
        print("  상위 탐지 유형:")
        for entry in report.top_entity_types:
            print(f"    {entry['type']}: {entry['count']}건")
        print()

    # 권고사항
    if report.recommendations:
        print("  권고사항:")
        for rec in report.recommendations:
            print(f"    - {rec}")
        print()

    # --- 3. Markdown 렌더링 -----------------------------------------
    print("[Markdown 리포트 미리보기]")
    md = render_security_markdown(report)
    lines = md.splitlines()
    for line in lines[:15]:
        print(f"  {line}")
    print(f"  ... (총 {len(lines)}줄)")
    print()

    # --- 4. JSON 렌더링 ---------------------------------------------
    print("[JSON 리포트]")
    import json
    json_str = render_security_json(report)
    parsed = json.loads(json_str)
    print(f"  최상위 키: {list(parsed.keys())}")
    print(f"  risk_level: {parsed['risk_level']}")

finally:
    shutil.rmtree(project_dir)
