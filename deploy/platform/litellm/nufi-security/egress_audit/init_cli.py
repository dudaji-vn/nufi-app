"""``nufi init`` — 프리셋에서 운영 config 를 구체화하는 CLI (CMP-121).

사용:
  nufi init <preset> [--out DIR] [--set k=v]... [--force]
  nufi init --list
  nufi init <preset> --dry-run        # 결정 미리보기(파일 미생성)

예:
  python -m egress_audit.init_cli strict-kr-pii --out ./config
  python -m egress_audit.init_cli audit-only --dry-run
  python -m egress_audit.init_cli pseudonymize-roundtrip --set policy.enforcement.fail_mode=closed

fail-closed: 알 수 없는 프리셋·override·검증 실패 시 비0 종료하며 파일을 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import yaml

from egress_audit import presets


def _print_list() -> int:
    names = presets.list_presets()
    if not names:
        print("(프리셋 없음)", file=sys.stderr)
        return 1
    for name in names:
        try:
            spec = presets.load_preset(name)
            desc = spec.get("description", "")
        except presets.PresetError:
            desc = "(로드 실패)"
        print(f"  {name:24s} {desc}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    if args.list or not args.preset:
        return _print_list()

    base_dir = Path(args.base_dir) if args.base_dir else None
    try:
        merged = presets.materialize(args.preset, base_dir=base_dir, overrides=args.set)
    except presets.PresetError as e:
        print(f"[init] 거부(fail-closed): {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"# nufi init {args.preset} — DRY RUN (파일 미생성)\n", file=sys.stderr)
        for key, fname in presets.BASE_FILES.items():
            print(f"# ===== {fname} =====")
            print(yaml.safe_dump(merged[key], allow_unicode=True,
                                 sort_keys=False, default_flow_style=False), end="")
        return 0

    out_dir = Path(args.out)
    try:
        written = presets.write_config(merged, out_dir, args.preset, force=args.force)
    except presets.PresetError as e:
        print(f"[init] 거부(fail-closed): {e}", file=sys.stderr)
        return 2
    print(f"[init] 프리셋 {args.preset!r} → {out_dir}")
    for p in written:
        print(f"  + {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="nufi init",
        description="파이프라인 프리셋에서 운영 config 를 구체화.")
    ap.add_argument("preset", nargs="?", help="프리셋 이름(생략 시 --list)")
    ap.add_argument("--list", action="store_true", help="사용 가능한 프리셋 목록")
    ap.add_argument("--out", default="config", help="config 출력 디렉터리(기본 ./config)")
    ap.add_argument("--base-dir", default=None, help="오버레이 베이스 config 디렉터리(기본 ./config)")
    ap.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="허용된 노브 override(반복 가능). 예 policy.enforcement.fail_mode=closed")
    ap.add_argument("--force", action="store_true", help="기존 config 파일 덮어쓰기")
    ap.add_argument("--dry-run", action="store_true", help="구체화 결과만 출력(파일 미생성)")
    ap.set_defaults(func=cmd_init)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
