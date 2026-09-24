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

UPDATE_API_BASE="https://api.github.com/repos/dudaji-vn/nufi-app"
UPDATE_CODELOAD_BASE="https://codeload.github.com/dudaji-vn/nufi-app/tar.gz"

# _update_protect_paths — sets UPDATE_PROTECT, the rsync excludes no copy in
# this file may cross: .env, caddy/mesh.caddy, any snapshot already sitting
# in .previous, the default data/ by name always, and — computed from where
# NUFI_DATA_DIR actually resolves, not assumed to be named "data" — the
# drives, the CA and schedules.ini.
#
# Anchored (a leading /): an unanchored `--exclude=data/` protects any
# directory named "data" anywhere in the tree, which both protects too much
# (a same-named directory two levels down that a release legitimately wants
# to change) and, for a NUFI_DATA_DIR that is not literally $HERE/data,
# protects nothing at all.
#
# Compared both as spelled (HERE and NUFI_DATA_DIR exactly as given) and as
# resolved (`pwd -P`, every symlink followed): HERE reached through a
# symlink while NUFI_DATA_DIR is physical, or the reverse, made the two
# strings disagree even though they name the same place on disk, so the
# comparison below checks every combination rather than trusting either
# alone. NUFI_DATA_DIR resolving to $HERE itself — a misconfiguration, not
# something an apply can protect its way around — is refused outright:
# every file under $HERE is "the tree" to a `rsync --delete` that excludes
# nothing, and that includes the drives, the CA, and the backup just taken.
#
# No trailing slash on the computed exclude: rsync's trailing-slash form
# matches a directory only, so `data -> /mnt/drives` as a symlink (a second
# disk for the drives) would not match `/data/` and would itself be deleted
# as "extraneous" — not its target's contents, `-a` never follows a symlink
# to delete through it, but the symlink entry itself. `/data` (no slash)
# matches a directory, a symlink, or a file at that path, whichever it is.
_update_protect_paths() {
  # /config/headscale.yaml and /Caddyfile.rendered protect a co-hosted
  # coordinator's rendered (gitignored) config from a --delete copy: the
  # release never ships them, bootstrap re-renders them, and the box tree has
  # no file at either path, so both are harmless for the deploy/box copy and
  # keep the coordinator copy from clobbering them mid-run. /data already
  # protects the coordinator's own data/ (its headscale DB), the same way it
  # protects the box's.
  UPDATE_PROTECT=(--exclude=/.env --exclude=/caddy/mesh.caddy --exclude=/.previous/ --exclude=/data \
    --exclude=/config/headscale.yaml --exclude=/Caddyfile.rendered)
  _dd="${NUFI_DATA_DIR:-$HERE/data}"
  _here_l="$HERE"
  _here_p="$(cd "$HERE" 2>/dev/null && pwd -P)" || _here_p="$_here_l"
  _dd_l="$(cd "$_dd" 2>/dev/null && pwd)" || _dd_l=""
  _dd_p="$(cd "$_dd" 2>/dev/null && pwd -P)" || _dd_p=""
  # Nothing there yet (a data dir an update runs before install-box.sh has
  # ever created it, which should not happen in practice -- backup_run,
  # called before any of this, already needs it to exist).
  [ -n "$_dd_l" ] || return 0

  for _h in "$_here_l" "$_here_p"; do
    for _d in "$_dd_l" "$_dd_p"; do
      [ "$_h" = "$_d" ] && die "NUFI_DATA_DIR is the box directory itself; move the data under \$HERE/data (nufi-box down, move, edit .env) before updating"
    done
  done

  _seen=""
  for _h in "$_here_l" "$_here_p"; do
    for _d in "$_dd_l" "$_dd_p"; do
      case "$_d/" in
        "$_h"/*)
          _rel="${_d#$_h/}"
          case "$_rel" in
            ""|/*|../*|*/../*) continue ;;
          esac
          case " $_seen " in
            *" $_rel "*) continue ;;
          esac
          _seen="$_seen $_rel"
          UPDATE_PROTECT+=(--exclude="/$_rel")
          ;;
      esac
    done
  done
}

# _update_copy SRC DST [EXTRA rsync args...] — mirror SRC onto DST: files DST
# has that SRC does not are deleted, files UPDATE_PROTECT names are left
# alone on DST whether or not SRC has them (rsync's documented behavior for
# --delete without --delete-excluded, which this never passes), and
# everything else is made to match SRC's content.
#
# --checksum, not the default quick check: a freshly extracted archive and a
# freshly written .previous/ tree can land on the same size and mtime as the
# files they are replacing (everything extracted or copied in the same
# second), and the quick check would then skip a real content change.
_update_copy() {
  _src="$1"; _dst="$2"; shift 2
  if [ "$DRY" != 1 ]; then
    command -v rsync >/dev/null 2>&1 || die "update: rsync is required to apply $_src onto $_dst"
  fi
  run mkdir -p "$_dst"
  run rsync -a --checksum --delete "${UPDATE_PROTECT[@]}" "$@" "$_src/" "$_dst/"
}

# _update_snapshot_images OUT — one line per service currently defined,
# "<service> <repo>@sha256:<digest> <repo>:<tag>": the digest is the
# reference `update --rollback` re-tags FROM, the trailing <repo>:<tag> is
# what it re-tags TO. Both are read from the same `docker compose images
# --format json` call — `docker compose config --images SVC` was tried first
# and rejected: it prints that service's whole dependency closure (its own
# image AND every image `depends_on` names), not just its own, so a two-line
# answer was fed to `docker tag` as if it were one reference and `set -e`
# killed the rollback partway through, right after the file copy.
#
# `docker compose images --format json` gives the image's local ID, which is
# the image's own config digest, not the manifest digest a `repo@sha256:...`
# reference needs; `docker image inspect` is what turns the ID into the
# RepoDigest that reference is built from. A service already pinned to a
# digest in the compose file (rag_api ships `@sha256:...`) answers an empty
# Tag — `docker tag` refuses a digest as its destination, so that service is
# named and skipped rather than attempted. A service with nothing running is
# skipped too — a box in that state already fails doctor, the check right
# after this.
_update_snapshot_images() {
  _out="$1"
  if [ "$DRY" = 1 ]; then
    printf '  $ %s images --format json <service>   # Repository, Tag and a digest resolved with docker image inspect, per service\n' "$COMPOSE"
    printf '  $ writing %s\n' "$_out"
    return 0
  fi
  : > "$_out"
  _svcs="$($COMPOSE config --services 2>/dev/null)" || _svcs=""
  for _svc in $_svcs; do
    _img_json="$($COMPOSE images --format json "$_svc" 2>/dev/null)" || _img_json=""
    if [ -z "$_img_json" ]; then echo "  $_svc: nothing running, skipped"; continue; fi
    _fields="$(printf '%s' "$_img_json" | python3 -c '
import json, sys
d = json.load(sys.stdin)
d = d[0] if d else {}
print(d.get("Repository", ""))
print(d.get("Tag", ""))
print(d.get("ID", ""))
' 2>/dev/null)" || _fields=""
    _repo="$(printf '%s\n' "$_fields" | sed -n 1p)"
    _tag="$(printf '%s\n' "$_fields" | sed -n 2p)"
    _id="$(printf '%s\n' "$_fields" | sed -n 3p)"
    if [ -z "$_repo" ] || [ -z "$_id" ]; then echo "  $_svc: no image found, skipped"; continue; fi
    if [ -z "$_tag" ]; then echo "  $_svc: pinned by digest in compose, skipped (docker tag cannot target a digest)"; continue; fi
    _digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$_id" 2>/dev/null)" || _digest=""
    if [ -z "$_digest" ]; then echo "  $_svc: no RepoDigest for $_id, skipped"; continue; fi
    echo "  $_svc: $_repo:$_tag"
    printf '%s %s %s:%s\n' "$_svc" "$_digest" "$_repo" "$_tag" >> "$_out"
  done
}

# _update_resolve_source REF — sets _download_url and _sha ("unknown" unless
# a real commit was resolved). NUFI_BOX_SOURCE, if the caller (or .env) set
# it, is a mirror for a box that cannot reach GitHub for the tarball either —
# used verbatim, no resolve attempted, sha unknown. Otherwise REF (or "main")
# is resolved to a commit sha through the GitHub API first, and the tarball
# is fetched BY THAT SHA — codeload accepts a bare sha, tag or branch name
# with no "refs/heads/" or "refs/tags/" prefix needed (checked against the
# real host). Resolving first is what makes "Updated to main (a1b2c3d)" true:
# without it the archive is whatever "main" pointed to at download time, a
# moving target with nothing pinning the message to what was actually
# fetched. The API is unauthenticated and rate-limited; offline or
# rate-limited, this falls back to fetching the ref directly and says so.
_update_resolve_source() {
  _sha="unknown"
  if [ -n "${NUFI_BOX_SOURCE:-}" ]; then
    _download_url="$NUFI_BOX_SOURCE"
    return 0
  fi
  _api_ref="${1:-main}"
  if [ "$DRY" = 1 ]; then
    printf '  $ curl %s/commits/%s   # resolve to a commit sha; falls back to fetching %s directly if the API is unreachable\n' \
      "$UPDATE_API_BASE" "$_api_ref" "$_api_ref"
    _download_url="$UPDATE_CODELOAD_BASE/$_api_ref"
    return 0
  fi
  _resolved="$(curl -fsS -m 10 "$UPDATE_API_BASE/commits/$_api_ref" 2>/dev/null | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("sha", ""))
except Exception:
    print("")
' 2>/dev/null)" || _resolved=""
  if [ -n "$_resolved" ]; then
    _download_url="$UPDATE_CODELOAD_BASE/$_resolved"
    _sha="${_resolved:0:7}"
  else
    echo "  could not resolve $_api_ref to a commit over the GitHub API — fetching it directly instead"
    _download_url="$UPDATE_CODELOAD_BASE/$_api_ref"
  fi
}

# _update_apply SRC_TOP — copy the three directories from an already
# extracted, already validated release onto this box: deploy/box over $HERE,
# and the two directories beside it (deploy/platform/scenarios WHOLE —
# build_flows.py imports run_box, which imports run, both siblings of
# studio/ at the root of scenarios/ — and deploy/platform/adapters/nufi-cron)
# over $(dirname "$HERE")/platform/…. litellm/config.yaml is excluded here
# only: the archive never ships a rendered one (it is gitignored), and
# install-box.sh re-renders it next regardless — but excluding it is what
# keeps a copy failure from being the thing that clobbers it.
_update_apply() {
  _src_top="$1"
  _update_copy "$_src_top/deploy/box" "$HERE" --exclude=/litellm/config.yaml || return 1
  _update_copy "$_src_top/deploy/platform/scenarios" "$_platform/scenarios" || return 1
  _update_copy "$_src_top/deploy/platform/adapters/nufi-cron" "$_platform/adapters/nufi-cron" || return 1
  # A --self-host-coordinator box has deploy/coordinator fetched beside
  # deploy/box (it is NOT in the box's own fetch set), so update it too — or
  # `nufi-box coordinator up` after an update would run stale coordinator
  # files. Gated: a plain box never fetched it, and its runtime state (data/,
  # .env, rendered config) is protected by UPDATE_PROTECT above.
  if [ "${NUFI_SELF_HOST_COORD:-0}" = 1 ]; then
    _update_copy "$_src_top/deploy/coordinator" "$_coordinator" || return 1
  fi
}

# update_run REF YES — fetch, snapshot, apply, re-install, check; roll back
# automatically when the check — or the installer, or the apply itself —
# fails.
update_run() {
  _ref="${1:-}"; _yes="${2:-0}"

  # First, before the prompt, the download or the backup: every copy in this
  # file goes through rsync, and dying here is cheaper than dying with a
  # backup already taken and an archive already downloaded. Real mode only —
  # a --dry-run's plan must not depend on what happens to be installed on
  # whatever machine is previewing it.
  if [ "$DRY" != 1 ]; then
    command -v rsync >/dev/null 2>&1 || die "rsync is required by nufi-box update: sudo apt-get install -y rsync"
    command -v python3 >/dev/null 2>&1 || die "python3 is required by nufi-box update"
  fi

  _label="${_ref:-main}"

  if [ "$_yes" != 1 ] && [ "$DRY" != 1 ]; then
    [ -t 0 ] || die "nufi-box update needs a terminal to confirm; pass --yes"
    echo "This backs up the box, replaces deploy/box and the two directories"
    echo "it depends on with $_label, re-runs the installer, and checks the"
    echo "result — rolling back automatically if the check fails."
    printf 'Type the box name (%s) to continue: ' "${BOX_NAME:-nufi}"
    read -r _answer
    [ "$_answer" = "${BOX_NAME:-nufi}" ] || die "not confirmed; nothing was changed"
  fi

  _platform="$(dirname "$HERE")/platform"
  _coordinator="$(dirname "$HERE")/coordinator"
  _update_protect_paths

  echo "Fetching $_label"
  echo "  not signed yet — this is GitHub over TLS, not a signed bundle (README \"What is not built yet\")"
  _update_resolve_source "$_label"
  _tmp="$(mktemp -d)"
  # A downloaded archive is left behind on every early exit below (a bad
  # download, an archive that is not a box) unless cleanup runs regardless of
  # how this scope is left — same reasoning, same trap, as install-box.sh's
  # gVisor download.
  trap 'rm -rf "$_tmp"' EXIT
  run curl -fsSL "$_download_url" -o "$_tmp/src.tar.gz" \
    || die "update: could not download $_download_url — nothing on the box was changed"
  # The WHOLE archive, not selected members: GNU tar (every Ubuntu box) does
  # not treat member names as globs without --wildcards, so `tar -xz
  # '*/deploy/box'` finds nothing and exits 2 there even though the same
  # command works on macOS's bsdtar. Extracting everything and copying the
  # three directories out in _update_apply is the portable way to get the
  # same three directories onto the box.
  run tar -xzf "$_tmp/src.tar.gz" -C "$_tmp" \
    || die "update: could not extract the archive from $_download_url — nothing on the box was changed"
  if [ "$DRY" = 1 ]; then
    printf '  $ python3 -c \x27import tarfile,sys; print(tarfile.open(sys.argv[1]).next().name.split("/")[0])\x27 %s/src.tar.gz   # the archive'"'"'s top directory\n' "$_tmp"
    _top="<top>"
  else
    _top="$(python3 -c '
import tarfile, sys
print(tarfile.open(sys.argv[1]).next().name.split("/")[0])
' "$_tmp/src.tar.gz" 2>/dev/null)"
    [ -n "$_top" ] || die "update: could not read the archive from $_download_url — nothing on the box was changed"
    [ -f "$_tmp/$_top/deploy/box/install-box.sh" ] \
      || die "update: the archive from $_download_url has no deploy/box/install-box.sh — nothing on the box was changed"
  fi

  echo "Backing up first: nufi-box backup"
  . "$HERE/lib/backup.sh"
  backup_run

  echo "Snapshotting the current tree, the routine builder and adapter, and image digests to $HERE/.previous"
  run rm -rf "$HERE/.previous"
  run mkdir -p "$HERE/.previous"
  _update_copy "$HERE" "$HERE/.previous/tree"
  if [ "$DRY" = 1 ] || [ -d "$_platform/scenarios" ]; then
    _update_copy "$_platform/scenarios" "$HERE/.previous/platform/scenarios"
  fi
  if [ "$DRY" = 1 ] || [ -d "$_platform/adapters/nufi-cron" ]; then
    _update_copy "$_platform/adapters/nufi-cron" "$HERE/.previous/platform/adapters/nufi-cron"
  fi
  # A self-host box's coordinator is snapshotted too, so a rollback puts back
  # the coordinator code that matched the box before the update (its data/ and
  # keys are protected, and never rolled back — same as the box's data).
  if [ "${NUFI_SELF_HOST_COORD:-0}" = 1 ] && { [ "$DRY" = 1 ] || [ -d "$_coordinator" ]; }; then
    _update_copy "$_coordinator" "$HERE/.previous/coordinator"
  fi
  _update_snapshot_images "$HERE/.previous/images.txt"
  # Last: this file existing is the whole test `update --rollback` makes
  # before trusting anything else under .previous/ — see I2 in the fix that
  # added it. A snapshot interrupted between here and the file copies above
  # must read as "no snapshot", not as one missing its images or half its
  # tree.
  run touch "$HERE/.previous/COMPLETE"

  echo "Applying $_label"
  if ! _update_apply "$_tmp/$_top"; then
    echo "The apply failed partway through; rolling back"
    update_rollback
    exit 1
  fi
  rm -rf "$_tmp"

  echo "Re-running the installer"
  if ! run "$HERE/install-box.sh" --yes --no-trust; then
    echo "The installer failed; rolling back"
    update_rollback
    exit 1
  fi

  echo "Checking the result"
  if [ "$DRY" = 1 ]; then
    printf '  $ %s/nufi-box doctor\n' "$HERE"
    echo "  if doctor fails: rolls back automatically (nufi-box update --rollback)"
    return 0
  fi
  if "$HERE/nufi-box" doctor; then
    if [ "$_sha" = "unknown" ]; then _sha_say="sha unknown"; else _sha_say="$_sha"; fi
    echo "Updated to $_label ($_sha_say)"
    printf '%s %s\n' "$_sha" "$(date -u +%Y-%m-%d)" > "${NUFI_DATA_DIR:-$HERE/data}/updated-from"
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
  if [ "$DRY" != 1 ]; then
    command -v rsync >/dev/null 2>&1 || die "rsync is required by nufi-box update --rollback: sudo apt-get install -y rsync"
    [ -d "$HERE/.previous" ] || die "update --rollback: nothing to roll back to — no $HERE/.previous"
    [ -f "$HERE/.previous/COMPLETE" ] \
      || die "update --rollback: the last snapshot is incomplete; nothing to roll back to"
  fi

  _platform="$(dirname "$HERE")/platform"
  _coordinator="$(dirname "$HERE")/coordinator"
  _update_protect_paths

  echo "Rolling back to what was here before the last update"
  _update_copy "$HERE/.previous/tree" "$HERE"
  if [ "$DRY" = 1 ] || [ -d "$HERE/.previous/platform/scenarios" ]; then
    _update_copy "$HERE/.previous/platform/scenarios" "$_platform/scenarios"
  fi
  if [ "$DRY" = 1 ] || [ -d "$HERE/.previous/platform/adapters/nufi-cron" ]; then
    _update_copy "$HERE/.previous/platform/adapters/nufi-cron" "$_platform/adapters/nufi-cron"
  fi
  # Put back a self-host box's coordinator code if it was snapshotted (its
  # data/ and keys were protected and were never touched).
  if [ -d "$HERE/.previous/coordinator" ] || { [ "$DRY" = 1 ] && [ "${NUFI_SELF_HOST_COORD:-0}" = 1 ]; }; then
    _update_copy "$HERE/.previous/coordinator" "$_coordinator"
  fi
  run rm -f "${NUFI_DATA_DIR:-$HERE/data}/updated-from"

  echo "  re-tagging images"
  if [ "$DRY" = 1 ]; then
    printf '  $ docker tag <repo>@sha256:...  <repo>:<tag>   # for every line in .previous/images.txt, tag recorded at snapshot time\n'
  elif [ -f "$HERE/.previous/images.txt" ]; then
    while read -r _svc _digest _tag_ref; do
      [ -n "$_svc" ] && [ -n "$_tag_ref" ] || continue
      # || not left to set -e: an image already pruned between the update
      # and a stand-alone --rollback must not take the rest of the rollback
      # down with it -- up -d and the doctor recheck below still matter even
      # when one service could not be re-tagged.
      run docker tag "$_digest" "$_tag_ref" \
        || echo "  $_svc: could not re-tag $_tag_ref (image gone?); continuing"
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
  # takes on its own. pipefail: backup_last's own grep returns 1 on an empty
  # backup directory, and that must not be this command's failure.
  . "$HERE/lib/backup.sh"
  _last="$(backup_last || true)"
  if [ -n "$_last" ]; then
    echo "Your data was backed up at $(_backup_dir)/$_last (its env is the one from before this update, and matches what is running now) — nufi-box restore $(_backup_dir)/$_last puts it back if you need it."
  fi

  if "$HERE/nufi-box" doctor; then
    echo "Rolled back. The box matches what was here before the update."
  else
    echo "Rolled back, but doctor still finds a problem — see above."
    return 1
  fi
}
