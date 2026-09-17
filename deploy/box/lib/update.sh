# Update and roll back the box. Sourced by nufi-box; uses its `run`, `die`,
# `COMPOSE`, `HERE` and the .env it already loaded. bash 3.2 compatible.
#
# NOT SIGNED YET. This pulls a tarball from GitHub over TLS — the same
# transport a browser gets, nothing more. There is no signature on the
# archive and nothing here checks one. A signed bundle served from
# updates.nufi.me is the next phase (see README.md "What is not built yet");
# until then, "update" means "trust GitHub and TLS", not "trust a bundle
# nufi-box has verified".
#
# Why this re-runs install-box.sh instead of growing a second apply path: the
# installer already knows how to keep .env and every secret and answer,
# re-render litellm/config.yaml, pull the images, bring the stack up,
# re-install the Studio routines, register Works when NUFI_WORKS=1, and
# rejoin the mesh. A second copy of any of that — written here, exercised
# only on update — is exactly the kind of code that drifts from the path
# every install and every day-two repair actually runs. Update's own job is
# small: fetch the new files, snapshot what is here now, lay the new files
# down, and hand the rest to install-box.sh.
#
# Why the databases are backed up here but never restored automatically: an
# update's migrations are meant to carry the data forward across the gap. A
# restore throws away everything written since the backup was taken — every
# message, every upload since then — which is a call for whoever is holding
# the backup's path to make on purpose, not something a failed health check
# should ever decide on its own.

UPDATE_SOURCE_DEFAULT="https://codeload.github.com/dudaji-vn/nufi-app/tar.gz/refs/heads/main"

# The three directories a box needs to be whole: itself, the routine builder
# `flows install` shells out to (deploy/platform/scenarios/studio), and the
# adapter `schedule list` reads (deploy/platform/adapters/nufi-cron). Fetching
# only deploy/box is the outside-developer install that ends with "the
# routines are not in Studio yet" — see this commit. Single-quoted in the
# design this copies and quoted the same way here: these are tar's own member
# patterns, not the shell's, and an unquoted `*/deploy/box` would be a glob
# against whatever the caller's cwd happens to hold.
UPDATE_TAR_PATTERNS=('*/deploy/box' '*/deploy/platform/scenarios/studio' '*/deploy/platform/adapters/nufi-cron')

# Paths a running box owns that an update must never touch: the secrets, the
# department's own documents, the mesh address this box was handed, any
# snapshot already sitting there, and the one file install-box.sh always
# re-renders itself (shipping a stale copy of it would fight that render).
UPDATE_EXCLUDE=(--exclude=.env --exclude=data/ --exclude=caddy/mesh.caddy --exclude=.previous/ --exclude=litellm/config.yaml)

# _update_copy SRC DST — mirror SRC onto DST: files DST has that SRC does not
# are deleted, files the exclude list names are left alone on DST whether or
# not SRC has them (rsync's documented behavior for --delete without
# --delete-excluded, which this never passes), and everything else is made to
# match SRC's content.
#
# --checksum, not the default quick check: a freshly extracted archive and a
# freshly written .previous/ tree can land on the same size and mtime as the
# files they are replacing (everything extracted or copied in the same
# second), and the quick check would then skip a real content change.
_update_copy() {
  command -v rsync >/dev/null 2>&1 || die "update: rsync is required to apply $1 onto $2"
  run rsync -a --checksum --delete "${UPDATE_EXCLUDE[@]}" "$1/" "$2/"
}

# _update_snapshot_images OUT — one line per service currently defined,
# "<service> <repo>@sha256:<digest>": the reference `update --rollback`
# re-tags from. `docker compose images --format json` gives the image's local
# ID, which is the image's own config digest, not the manifest digest a
# `repo@sha256:...` reference needs; `docker image inspect` is what turns the
# ID into the RepoDigest that reference is built from. A service with nothing
# running (nothing to snapshot) is skipped rather than failing the whole
# update — a box in that state already fails doctor, which is the check right
# after this.
_update_snapshot_images() {
  _out="$1"
  if [ "$DRY" = 1 ]; then
    printf '  $ %s images --format json <service>   # resolved to a digest with docker image inspect, per service\n' "$COMPOSE"
    printf '  $ writing %s\n' "$_out"
    return 0
  fi
  : > "$_out"
  _svcs="$($COMPOSE config --services 2>/dev/null)" || _svcs=""
  for _svc in $_svcs; do
    _img_json="$($COMPOSE images --format json "$_svc" 2>/dev/null)" || _img_json=""
    [ -n "$_img_json" ] || continue
    _repo_id="$(printf '%s' "$_img_json" | python3 -c '
import json, sys
d = json.load(sys.stdin)
d = d[0] if d else {}
print(d.get("Repository", ""))
print(d.get("ID", ""))
' 2>/dev/null)" || _repo_id=""
    _repo="$(printf '%s\n' "$_repo_id" | sed -n 1p)"
    _id="$(printf '%s\n' "$_repo_id" | sed -n 2p)"
    [ -n "$_repo" ] && [ -n "$_id" ] || continue
    _digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$_id" 2>/dev/null)" || _digest=""
    [ -n "$_digest" ] || continue
    printf '%s %s\n' "$_svc" "$_digest" >> "$_out"
  done
}

# update_run REF YES — fetch, snapshot, apply, re-install, check; roll back
# automatically when the check fails.
update_run() {
  _ref="${1:-}"; _yes="${2:-0}"

  _src="${NUFI_BOX_SOURCE:-$UPDATE_SOURCE_DEFAULT}"
  if [ -n "$_ref" ]; then
    case "$_src" in
      */refs/heads/*) _src="${_src%/refs/heads/*}/refs/tags/$_ref" ;;
      *) die "update --ref: NUFI_BOX_SOURCE does not end in /refs/heads/<something> to rewrite to a tag: $_src" ;;
    esac
  fi
  _label="${_ref:-main}"

  if [ "$_yes" != 1 ] && [ "$DRY" != 1 ]; then
    echo "This backs up the box, replaces deploy/box and the two directories"
    echo "it depends on with $_label, re-runs the installer, and checks the"
    echo "result — rolling back automatically if the check fails."
    printf 'Type the box name (%s) to continue: ' "${BOX_NAME:-nufi}"
    read -r _answer
    [ "$_answer" = "${BOX_NAME:-nufi}" ] || die "not confirmed; nothing was changed"
  fi

  echo "Fetching $_label"
  echo "  not signed yet — this is GitHub over TLS, not a signed bundle (README \"What is not built yet\")"
  _tmp="$(mktemp -d)"
  # A downloaded archive is left behind on every early exit below (a bad
  # download, an archive that is not a box) unless cleanup runs regardless of
  # how this scope is left — same reasoning, same trap, as install-box.sh's
  # gVisor download.
  trap 'rm -rf "$_tmp"' EXIT
  run curl -fsSL "$_src" -o "$_tmp/box.tar.gz" \
    || die "update: could not download $_src — nothing on the box was changed"
  run mkdir -p "$_tmp/extract"
  run tar -xz --strip-components=1 -C "$_tmp/extract" -f "$_tmp/box.tar.gz" "${UPDATE_TAR_PATTERNS[@]}" \
    || die "update: could not extract the archive from $_src — nothing on the box was changed"
  if [ "$DRY" = 1 ]; then
    printf '  $ test -f %s/extract/deploy/box/install-box.sh   # refuse an archive that is not a box\n' "$_tmp"
  else
    [ -f "$_tmp/extract/deploy/box/install-box.sh" ] \
      || die "update: the archive from $_src has no deploy/box/install-box.sh — nothing on the box was changed"
    # The tarball's own top directory names the commit this archive is —
    # codeload names it <repo>-<short-sha> however the ref was spelled, so
    # this is read once, here, before --strip-components throws it away.
    _sha="$(tar -tzf "$_tmp/box.tar.gz" 2>/dev/null | head -1)"
    _sha="${_sha%%/*}"; _sha="${_sha#nufi-app-}"
  fi

  echo "Backing up first: nufi-box backup"
  . "$HERE/lib/backup.sh"
  backup_run

  echo "Snapshotting the current tree and image digests to $HERE/.previous"
  run rm -rf "$HERE/.previous"
  run mkdir -p "$HERE/.previous"
  _update_copy "$HERE" "$HERE/.previous"
  _update_snapshot_images "$HERE/.previous/images.txt"

  echo "Applying $_label"
  _update_copy "$_tmp/extract/deploy/box" "$HERE"
  _platform="$(dirname "$HERE")/platform"
  run mkdir -p "$_platform/scenarios"
  _update_copy "$_tmp/extract/deploy/platform/scenarios/studio" "$_platform/scenarios/studio"
  run mkdir -p "$_platform/adapters"
  _update_copy "$_tmp/extract/deploy/platform/adapters/nufi-cron" "$_platform/adapters/nufi-cron"
  rm -rf "$_tmp"

  echo "Re-running the installer"
  run "$HERE/install-box.sh" --yes --no-trust

  echo "Checking the result"
  if [ "$DRY" = 1 ]; then
    printf '  $ %s/nufi-box doctor\n' "$HERE"
    echo "  if doctor fails: rolls back automatically (nufi-box update --rollback)"
    return 0
  fi
  if "$HERE/nufi-box" doctor; then
    echo "Updated to $_label ($_sha)"
    printf '%s %s\n' "$_sha" "$(date -u +%Y-%m-%d)" > "$HERE/.previous/updated-from"
  else
    echo "The health check above failed; rolling back"
    update_rollback
    exit 1
  fi
}

# update_rollback — put back what update_run (or an earlier one) snapshotted.
# Also `nufi-box update --rollback` on its own, for a box someone wants back
# even without a fresh update having just failed.
update_rollback() {
  # Real only: a --dry-run always shows the plan a rollback would run, the
  # same way `update`'s own dry-run plan never depends on whether the archive
  # it would fetch actually exists.
  if [ "$DRY" != 1 ]; then
    [ -d "$HERE/.previous" ] || die "update --rollback: nothing to roll back to — no $HERE/.previous"
  fi

  echo "Rolling back to what was here before the last update"
  _update_copy "$HERE/.previous" "$HERE"

  echo "  re-tagging images"
  if [ "$DRY" = 1 ]; then
    printf '  $ docker tag <repo>@sha256:...  <repo>:<tag>   # for every line in .previous/images.txt, tag read from %s config --images\n' "$COMPOSE"
  elif [ -f "$HERE/.previous/images.txt" ]; then
    while read -r _svc _digest; do
      [ -n "$_svc" ] || continue
      _tag_ref="$($COMPOSE config --images "$_svc" 2>/dev/null)" || _tag_ref=""
      [ -n "$_tag_ref" ] || continue
      run docker tag "$_digest" "$_tag_ref"
    done < "$HERE/.previous/images.txt"
  fi

  . "$HERE/lib/mesh.sh"
  mesh_caddy_refresh "$HERE"
  run $COMPOSE up -d

  echo "Checking the rollback"
  if [ "$DRY" = 1 ]; then
    printf '  $ %s/nufi-box doctor\n' "$HERE"
    return 0
  fi

  # A rollback undoes the code and the running images; it never touches the
  # backup taken in step 2a — the data since then is real and a restore is a
  # decision for a person holding this path, not something a failed check
  # takes on its own.
  . "$HERE/lib/backup.sh"
  _last="$(backup_last)"
  if [ -n "$_last" ]; then
    echo "Your data was backed up at $(_backup_dir)/$_last — nufi-box restore $(_backup_dir)/$_last puts it back if you need it."
  fi

  if "$HERE/nufi-box" doctor; then
    echo "Rolled back. The box matches what was here before the update."
  else
    echo "Rolled back, but doctor still finds a problem — see above."
    return 1
  fi
}
