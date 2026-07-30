#!/usr/bin/env bash
# 인젝션 탐지 벤치마크 — 재현율·정밀도 측정 (30건 골드셋)
# bench_injection.py 를 demo_all.sh 에서 실행 가능하게 감싼 래퍼.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/bench_injection.py "$@"
