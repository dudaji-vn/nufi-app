#!/usr/bin/env bash
# 에어갭 번들 빌더 (CMP-122 / NFR1).
# 인터넷 연결된 빌드 호스트에서 실행 → 오프라인 설치용 단일 tar.gz 산출.
#
#   bash deploy/airgap/build-bundle.sh [--heavy] [--out DIR]
#
# 산출물(<out>/nufi-egress-audit-<tag>[-heavy]-airgap.tar.gz)에 포함:
#   - images.tar         : docker save 한 런타임 이미지(레지스트리 불필요)
#   - deploy/            : compose 파일·.env.example·Helm 차트
#   - INSTALL.md         : 오프라인 설치 절차
#   - MANIFEST.txt       : 태그·다이제스트·sha256 무결성
set -euo pipefail

HEAVY=0
OUT_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --heavy) HEAVY=1; shift ;;
    --out)   OUT_DIR="${2:?--out 인자 필요}"; shift 2 ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# compose 기본 태그와 일치(NUFI_TAG 로 오버라이드). VERSION 은 릴리스 전까지 0.0.1 이므로
# 배포 아티팩트 태그는 마일스톤(0.0.2-dev)에 고정한다.
TAG="${NUFI_TAG:-0.0.2-dev}"
IMAGE="nufi-egress-audit:${TAG}"
COMPOSE_ARGS=(-f deploy/docker-compose.yml)
if [[ "$HEAVY" == "1" ]]; then
  IMAGE="nufi-egress-audit:${TAG}-heavy"
  COMPOSE_ARGS+=(-f deploy/docker-compose.heavy.yml)
fi

OUT_DIR="${OUT_DIR:-$REPO_ROOT/dist}"
mkdir -p "$OUT_DIR"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "[1/4] 이미지 빌드: $IMAGE"
NUFI_TAG="$TAG" docker compose "${COMPOSE_ARGS[@]}" build

echo "[2/4] 이미지 저장(docker save): images.tar"
docker save -o "$STAGE/images.tar" "$IMAGE"

echo "[3/4] deploy 아티팩트 + 설치 가이드 스테이징"
mkdir -p "$STAGE/deploy"
cp -r deploy/docker-compose.yml deploy/docker-compose.heavy.yml \
      deploy/.env.example deploy/helm "$STAGE/deploy/"
cp deploy/airgap/load-bundle.sh "$STAGE/"
cp deploy/airgap/INSTALL.md "$STAGE/INSTALL.md"

{
  echo "# NuFi Egress-Audit 에어갭 번들 MANIFEST"
  echo "tag: $TAG"
  echo "image: $IMAGE"
  echo "heavy_backend: $([[ "$HEAVY" == 1 ]] && echo yes || echo no)"
  echo "image_id: $(docker image inspect "$IMAGE" --format '{{.Id}}')"
  echo "images_tar_sha256: $(sha256sum "$STAGE/images.tar" | awk '{print $1}')"
} > "$STAGE/MANIFEST.txt"

SUFFIX=$([[ "$HEAVY" == 1 ]] && echo "-heavy" || echo "")
BUNDLE="$OUT_DIR/nufi-egress-audit-${TAG}${SUFFIX}-airgap.tar.gz"
echo "[4/4] 번들 패키징: $BUNDLE"
tar -C "$STAGE" -czf "$BUNDLE" .

echo
echo "완료. 에어갭 호스트로 전송할 단일 파일:"
echo "  $BUNDLE"
echo "  크기: $(du -h "$BUNDLE" | awk '{print $1}')"
