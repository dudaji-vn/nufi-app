"""NuFi Python SDK — 한국 규제 증빙 리포트 예시.

compliance_report / render_report / load_catalog 를 사용합니다.
자세한 API 문서: docs/SDK.md § 2.5, docs/REPORTING.md

실행:
    python3 examples/sdk_compliance_report.py
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from nufi import compliance_report, render_report, load_catalog

# --- 1. 통제 카탈로그 로드 -------------------------------------------
print("[통제 카탈로그]")
catalog = load_catalog()
controls = catalog.get("controls", [])
by_fw: dict = {}
for c in controls:
    fw = c.get("framework", "unknown")
    by_fw.setdefault(fw, 0)
    by_fw[fw] += 1

print(f"  총 통제: {len(controls)}개")
for fw, cnt in sorted(by_fw.items()):
    label = {
        "fsec-ai": "금융 AI 안내서",
        "net-sep": "망분리 보안대책",
        "pipa": "개인정보보호법",
        "cia": "신용정보법",
        "isms-p": "ISMS-P",
    }.get(fw, fw)
    print(f"  {label}: {cnt}개")
print()

# --- 2. 규정준수 리포트 생성 (점검항목 커버리지 포함) ----------------
print("[규정준수 리포트 생성]")
model = compliance_report(controls=True)

# 해시체인 무결성
integrity = "OK" if model.get("integrity_ok") else "위반(감사로그 없거나 변조)"
print(f"  해시체인 무결성: {integrity}")

# 통제 커버리지 요약
cov = model.get("control_coverage", {})
summary = cov.get("summary", {})
if summary:
    direct = summary.get("direct", 0)
    direct_met = summary.get("direct_met", 0)
    partial = summary.get("partial", 0)
    oos = summary.get("out_of_scope", 0)
    print(f"  직접 통제: {direct}개 (충족 {direct_met} / 미충족 {direct - direct_met})")
    print(f"  부분 충족: {partial}개 | 범위 외: {oos}개")

    by_framework = summary.get("by_framework", {})
    print("\n  프레임워크별 충족 현황:")
    label_map = {
        "fsec-ai": "금융 AI 안내서",
        "net-sep": "망분리",
        "pipa":    "개인정보보호법",
        "cia":     "신용정보법",
        "isms-p":  "ISMS-P",
    }
    for fw, fwdata in by_framework.items():
        met = fwdata.get("direct_met", 0)
        total_direct = fwdata.get("direct", 0)
        bar = "✅" if total_direct > 0 and met == total_direct else "🟡"
        print(f"    {bar} {label_map.get(fw, fw)}: {met}/{total_direct} direct 충족")
print()

# --- 3. 리포트를 Markdown / JSON 으로 렌더링 ------------------------
print("[리포트 렌더링]")
md_out = render_report(model, fmt="md")
lines = md_out.splitlines()
# 첫 10줄만 미리보기
print("  (Markdown 앞 10줄 미리보기)")
for line in lines[:10]:
    print(f"    {line}")
print(f"  ... ({len(lines)}줄 전체)")
print()

# JSON 형식도 가능
import json as _json
json_out = render_report(model, fmt="json")
parsed = _json.loads(json_out)
print(f"  JSON 산출물 최상위 키: {list(parsed.keys())}")
