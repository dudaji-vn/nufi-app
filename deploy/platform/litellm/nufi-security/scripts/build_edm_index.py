#!/usr/bin/env python3
"""EDM 인덱스 빌더 (오프라인 배치, SPEC_M4 §3).

register.yaml 의 등록 명세를 읽어 셀 해시/문서 시그니처 인덱스를 만든다.
인라인 게이트웨이 경로와 분리(NFR1): 원문은 인덱스에 저장하지 않는다 —
출력 index.json 에는 해시·MinHash 시그니처·필드명·임계값만 들어간다.

사용:
    python3 scripts/build_edm_index.py [register.yaml] [out_index.json]
기본 경로: config/edm/register.yaml → config/edm/index.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from egress_audit import edm  # noqa: E402


def _read_csv(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build(register_path: Path) -> dict:
    reg = yaml.safe_load(register_path.read_text(encoding="utf-8")) or {}
    th = reg.get("thresholds", {})

    struct = []
    for ds in reg.get("structured", []) or []:
        rows = _read_csv(ROOT / ds["csv"])
        struct.append(edm.register_structured(
            rows, ds["fields"], dataset=ds["dataset"]))

    docs = []
    for d in reg.get("documents", []) or []:
        text = (ROOT / d["file"]).read_text(encoding="utf-8")
        docs.append(edm.register_document(
            text, doc_id=d["doc_id"], cls=d.get("class", "CONFIDENTIAL"),
            k=int(d.get("k", 8)), window=int(d.get("window", 4)),
            num_perm=int(d.get("num_perm", 64))))

    stop_hashes = sorted({edm._cell_hash(v) for v in reg.get("stop_values", []) if v})

    return {
        "ruleset_version": reg.get("ruleset_version", "edm-2026.06.25"),
        "thresholds": {
            "k_of_n": int(th.get("k_of_n", 2)),
            "doc_high": float(th.get("doc_high", 0.45)),
            "doc_med": float(th.get("doc_med", 0.22)),
        },
        "stop_hashes": stop_hashes,
        "struct": struct,
        "docs": docs,
    }


def main() -> int:
    reg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "edm" / "register.yaml"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "config" / "edm" / "index.json"
    index = build(reg_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=0), encoding="utf-8")
    n_struct = sum(len(s.get("records", [])) for s in index["struct"])
    print(f"[edm] built index → {out_path}")
    print(f"[edm] structured datasets={len(index['struct'])} records={n_struct} "
          f"docs={len(index['docs'])} stop_hashes={len(index['stop_hashes'])}")
    print(f"[edm] ruleset_version={index['ruleset_version']} (원문 미저장 — 해시/시그니처만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
