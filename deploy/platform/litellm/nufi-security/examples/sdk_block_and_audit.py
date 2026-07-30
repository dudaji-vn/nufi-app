"""CMP-119 수용기준 2 — 민감정보 요청 SDK 경유 시 403 차단 + 감사 1건 적재.

격리된 감사 로그 경로로 NuFi 를 만들어, 차단 전후 감사 레코드 수를 비교한다.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 소스 실행용(pip 설치 시 불필요)

import tempfile
from pathlib import Path

from egress_audit import AuditLogger
from nufi_client import NuFi, NuFiBlocked

audit_path = Path(tempfile.gettempdir()) / "nufi_sdk_block_demo.jsonl"
audit_path.unlink(missing_ok=True)

client = NuFi(audit_log=str(audit_path))
before = len(AuditLogger(path=str(audit_path)).read_all())

try:
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content":
                   "AWS 키 좀 봐줘: AKIAIOSFODNN7EXAMPLE / "
                   "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}])
    print("FAIL: 차단되지 않음")
except NuFiBlocked as e:
    after = AuditLogger(path=str(audit_path)).read_all()
    print(f"차단됨(403): entities={e.entities} audit_id={e.audit_id}")
    print(f"감사 적재: {len(after) - before}건 (총 {len(after)})")
    rec = after[-1]
    print(f"감사 레코드: outcome={rec['outcome']} is_public={rec['is_public']} "
          f"model={rec['model']}")
    assert len(after) - before == 1 and rec["outcome"] == "blocked"
    print("OK — 403 차단 + 감사 1건 적재 확인")
