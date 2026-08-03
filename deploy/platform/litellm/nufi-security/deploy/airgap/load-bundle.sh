#!/usr/bin/env bash
# 에어갭 번들 로더 (CMP-122 / NFR1).
# 번들을 푼 디렉터리(이 스크립트가 들어있는 곳)에서 오프라인 호스트에서 실행.
#
#   tar -xzf nufi-egress-audit-<tag>-airgap.tar.gz -C nufi && cd nufi
#   bash load-bundle.sh            # docker load + 무결성 확인
#   docker compose -f deploy/docker-compose.yml up -d   # 기동
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -f images.tar ]]; then
  echo "images.tar 없음 — 번들이 올바르게 풀렸는지 확인하세요." >&2
  exit 1
fi

if [[ -f MANIFEST.txt ]]; then
  EXPECT="$(awk -F': ' '/images_tar_sha256/{print $2}' MANIFEST.txt)"
  if [[ -n "${EXPECT:-}" ]]; then
    echo "[*] 무결성 검증(sha256)…"
    ACTUAL="$(sha256sum images.tar | awk '{print $1}')"
    if [[ "$ACTUAL" != "$EXPECT" ]]; then
      echo "무결성 불일치! expected=$EXPECT actual=$ACTUAL" >&2
      exit 1
    fi
    echo "    OK ($ACTUAL)"
  fi
fi

echo "[*] 이미지 로드(docker load)…"
docker load -i images.tar

echo
echo "로드 완료. 기동:"
echo "  cp deploy/.env.example deploy/.env   # 필요시 포트/태그 조정"
echo "  docker compose -f deploy/docker-compose.yml up -d"
echo "  curl -fsS http://localhost:4000/health   # {\"status\":\"ok\"} → GREEN"
