#!/usr/bin/env bash
# =============================================================================
# GitHub Release 발행 (릴리스 메커닉 — 태그 푸시 직후 필수 단계)
#
# git 태그만 origin 에 올리던 기존 메커닉이 누락하던 단계:
# GitHub Release 객체(노트 본문 포함)를 태그에 발행한다.
#
# 본문(notes) = docs/RELEASE_NOTES.md 의 해당 버전 섹션(사람 친화 6-섹션 내러티브).
# 제목(title) = 해당 git 태그의 annotation subject.
#
# 인증: gh CLI(로그인됨) 또는 환경변수 GH_TOKEN/GITHUB_TOKEN(repo scope) 필요.
#       둘 다 없으면 발행 불가 — 본문 파일만 추출해 두고 안내 후 종료(코드 2).
#
# 사용:
#   ./scripts/publish_github_release.sh v0.0.6            # 발행
#   ./scripts/publish_github_release.sh v0.0.6 --dry-run  # 본문만 추출·미발행
# =============================================================================
set -euo pipefail

REPO="dudaji/nufi-security"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTES_SRC="$ROOT/docs/RELEASE_NOTES.md"

TAG="${1:-}"
DRY_RUN="${2:-}"
if [[ -z "$TAG" ]]; then
  echo "사용법: $0 vX.Y.Z [--dry-run]" >&2
  exit 64
fi

# 0) 태그가 origin 에 존재하는지 확인.
if ! git -C "$ROOT" rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "오류: 로컬에 태그 $TAG 가 없습니다. 먼저 태그를 컷·푸시하세요." >&2
  exit 65
fi

# 1) 제목 = 태그 annotation subject (lightweight 태그면 헤딩으로 폴백).
TITLE="$(git -C "$ROOT" for-each-ref "refs/tags/$TAG" --format='%(contents:subject)')"

# 2) 본문 = RELEASE_NOTES.md 의 "## <TAG> …" 섹션(다음 '---' 직전까지).
NOTES_FILE="$(mktemp -t "release-notes-$TAG.XXXXXX.md")"
awk -v tag="$TAG" '
  $0 ~ "^## " tag "([ \t]|$)" {grab=1}
  grab && /^---[ \t]*$/ {exit}
  grab {print}
' "$NOTES_SRC" > "$NOTES_FILE"

if [[ ! -s "$NOTES_FILE" ]]; then
  echo "오류: $NOTES_SRC 에서 '## $TAG' 섹션을 찾지 못했습니다." >&2
  echo "      RELEASE_NOTES.md 에 해당 버전 섹션이 있는지 확인하세요." >&2
  rm -f "$NOTES_FILE"
  exit 66
fi

echo "제목 : ${TITLE:-$TAG}"
echo "본문 : $NOTES_FILE ($(wc -l < "$NOTES_FILE") 줄)"

if [[ "$DRY_RUN" == "--dry-run" ]]; then
  echo "[--dry-run] 발행하지 않음. 본문 미리보기:"
  echo "------------------------------------------------------------"
  cat "$NOTES_FILE"
  echo "------------------------------------------------------------"
  echo "발행하려면: $0 $TAG"
  exit 0
fi

# 3) 발행 — gh CLI 우선, 없으면 REST API(curl + 토큰).
if command -v gh >/dev/null 2>&1; then
  echo "→ gh release create $TAG"
  gh release create "$TAG" \
    --repo "$REPO" \
    --title "${TITLE:-$TAG}" \
    --notes-file "$NOTES_FILE" \
    --verify-tag
  echo "발행 완료: https://github.com/$REPO/releases/tag/$TAG"
  rm -f "$NOTES_FILE"
  exit 0
fi

TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [[ -n "$TOKEN" ]]; then
  echo "→ REST API (curl) POST /repos/$REPO/releases"
  # jq 없이도 동작하도록 본문을 안전하게 JSON 인코딩(python3 사용).
  PAYLOAD="$(TITLE="${TITLE:-$TAG}" TAG="$TAG" NOTES_FILE="$NOTES_FILE" python3 - <<'PY'
import json, os
print(json.dumps({
    "tag_name": os.environ["TAG"],
    "name": os.environ["TITLE"],
    "body": open(os.environ["NOTES_FILE"], encoding="utf-8").read(),
    "draft": False,
    "prerelease": False,
}))
PY
)"
  HTTP_CODE="$(curl -sS -o /tmp/gh_release_resp.json -w '%{http_code}' \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$REPO/releases" \
    -d "$PAYLOAD")"
  if [[ "$HTTP_CODE" == "201" ]]; then
    echo "발행 완료(201): https://github.com/$REPO/releases/tag/$TAG"
    rm -f "$NOTES_FILE"
    exit 0
  fi
  echo "오류: REST API 응답 HTTP $HTTP_CODE" >&2
  cat /tmp/gh_release_resp.json >&2
  rm -f "$NOTES_FILE"
  exit 1
fi

# 4) 인증 없음 — 본문만 남기고 안내.
echo "" >&2
echo "발행 불가: gh CLI 도, GH_TOKEN/GITHUB_TOKEN 환경변수도 없습니다." >&2
echo "본문은 추출해 두었습니다: $NOTES_FILE" >&2
echo "토큰 확보 후 둘 중 하나로 발행하세요:" >&2
echo "  gh release create $TAG --repo $REPO --title \"${TITLE:-$TAG}\" --notes-file \"$NOTES_FILE\"" >&2
echo "  GH_TOKEN=<repo-scope-토큰> $0 $TAG" >&2
exit 2
