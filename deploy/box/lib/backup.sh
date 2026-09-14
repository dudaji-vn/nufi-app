# Backup and restore for the box. Sourced by nufi-box; uses its `run`, `die`,
# `COMPOSE`, `HERE` and the .env it already loaded.
#
# What a backup has to contain is decided by what a restore needs, which is more
# than the plan's "pg_dumpall and mongodump". A box rebuilt from two database
# dumps comes up with every account and every agent and **no documents**, which
# is the one thing the department actually put there. It also comes up with new
# secrets, so the sessions, the signed tokens and the certificate a laptop was
# told to trust are all strangers to it.
#
# So: the two dumps, the drives, the files people attached in the app, Studio's
# own file store, the certificate authority, and .env.
#
# That last one means **a backup holds the box's secrets in clear**. It is
# written 0600 into a directory the installer makes 0700, and the README says
# plainly that a copy on a USB disk is the box's keys in someone's pocket.

BACKUP_KEEP_DEFAULT=7

_backup_dir() { echo "${NUFI_DATA_DIR:?NUFI_DATA_DIR is not set}/backup"; }

# The newest backup, for `nufi-box status`. Prints nothing when there is none:
# a box that has never been backed up should say so in the status line rather
# than here.
backup_last() {
  _d="$(_backup_dir)"
  [ -d "$_d" ] || return 0
  ls -1 "$_d" 2>/dev/null | grep -E '^[0-9]{8}-[0-9]{6}$' | sort | tail -1
}

backup_run() {
  # Checked here, before anything is written. Under `set -u` an absent
  # MONGO_PASSWORD killed this script on the mongodump line -- after the
  # postgres dump had already been written, leaving a directory that looks like
  # a backup and is half of one. Say what is wrong while there is still nothing
  # on disk to mistake for a backup.
  _mongo_pw="${MONGO_PASSWORD:-}"
  if [ -z "$_mongo_pw" ] && [ "$DRY" != 1 ]; then
    die "MONGO_PASSWORD is not in $ENVF — mongodump cannot authenticate, and would leave an empty archive behind"
  fi
  _to="${BACKUP_TO:-$(_backup_dir)}"
  _keep="${BACKUP_KEEP:-$BACKUP_KEEP_DEFAULT}"
  _stamp="$(date -u +%Y%m%d-%H%M%S)"
  _out="$_to/$_stamp"

  echo "Backing up to $_out"
  run mkdir -p "$_out"
  run chmod 700 "$_out"

  # Dumps go through the containers' own clients, so the host needs neither
  # postgres nor mongo tools installed -- the same reason `doctor` shells into
  # rag_api rather than importing anything here.
  #
  # pg_dumpall, not pg_dump: the box has several databases (the app's, Studio's,
  # LiteLLM's) and a per-database dump is one more thing to remember to add when
  # a service is added. Roles come with it, which a restore needs.
  # --clean, so the dump drops each database and role before recreating it.
  # Without it a restore onto a box that still has its databases is a MERGE:
  # psql reports "relation already exists" on every table, rows added since the
  # backup survive, and the restore reports success. It only looks right when
  # the box has not diverged from the backup -- which is exactly the case you
  # are not restoring for.
  echo "  postgres"
  run sh -c "$COMPOSE exec -T postgres pg_dumpall --clean -U '${POSTGRES_USER:-nufi}' | gzip > '$_out/postgres.sql.gz'"

  # --username/--password/--authenticationDatabase, because the box's mongo is
  # not open: a bare `mongodump` answers "(Unauthorized) command listDatabases
  # requires authentication" and -- since it writes the failure to stderr and an
  # empty archive to stdout -- leaves a plausible-looking 20-byte file behind.
  # That is the shape of backup bug nobody finds until a restore.
  echo "  mongodb"
  run sh -c "$COMPOSE exec -T mongodb mongodump --archive --gzip \
    --username '${MONGO_USER:-nufi}' --password '$_mongo_pw' \
    --authenticationDatabase admin > '$_out/mongodb.archive.gz'"

  # The drives are the department's own documents and the largest thing here.
  # `_routines` is excluded: those are reports the box generated and can
  # generate again, and they would grow every backup for ever.
  echo "  drives"
  run sh -c "tar -czf '$_out/drives.tar.gz' --exclude '_routines' -C '${NUFI_DATA_DIR}' drives"

  # Volumes, through a throwaway container, because they are docker-managed and
  # have no path on the host to tar.
  #
  # caddy-data is in this list for a reason worth writing down: the box's real
  # certificate authority is in there (caddy/pki/authorities/local/root.key),
  # and `data/nufi-box-ca.crt` on the host is only the copy handed to laptops.
  # Restore without it and Caddy makes a NEW authority -- the box comes back up
  # perfectly, serving a certificate that every laptop told to trust the old one
  # now rejects.
  #
  # ingest-state is what nufi-ingest has already uploaded. Lose it and the
  # daemon re-uploads every document on every drive, so the department's agent
  # ends up holding two of everything.
  for _vol in app-uploads studio-data caddy-data ingest-state cron-state; do
    echo "  $_vol"
    run sh -c "docker run --rm -v 'nufi-box_$_vol:/v:ro' -v '$_out:/out' alpine:3.20 tar -czf '/out/$_vol.tar.gz' -C /v ."
  done

  echo "  certificate authority and .env"
  run sh -c "tar -czf '$_out/ca.tar.gz' -C '${NUFI_DATA_DIR}' \$(cd '${NUFI_DATA_DIR}' && ls | grep -E 'nufi-box-ca' | tr '\\n' ' ')"
  run sh -c "cp '$ENVF' '$_out/env' && chmod 600 '$_out/env'"

  run sh -c "cat > '$_out/MANIFEST' <<EOF
box:      ${BOX_NAME:-nufi} (${BOX_HOST:-?})
taken:    $_stamp UTC
model:    ${NUFI_MODEL:-?}
contents: postgres.sql.gz mongodb.archive.gz drives.tar.gz ca.tar.gz env
          app-uploads.tar.gz studio-data.tar.gz caddy-data.tar.gz
          ingest-state.tar.gz cron-state.tar.gz
restore:  nufi-box restore $_out

This directory contains the box's secrets in clear (env). Treat a copy of it
the way you would treat the box itself.
EOF"

  # Retention, because a box that fills its own disk with backups has made
  # things worse. Newest \$_keep kept; only the timestamped directories this
  # command makes are ever considered, so a --to directory holding other things
  # loses none of them.
  if [ "$_keep" -gt 0 ] 2>/dev/null; then
    for _old in $(ls -1 "$_to" 2>/dev/null | grep -E '^[0-9]{8}-[0-9]{6}$' | sort -r | tail -n +$((_keep + 1))); do
      echo "  pruning $_old"
      run rm -rf "$_to/$_old"
    done
  fi

  if [ "$DRY" = 1 ]; then echo "  (dry run: nothing was written)"; return 0; fi
  echo
  echo "Done. $(du -sh "$_out" 2>/dev/null | cut -f1) in $_out"
  echo "Restore it with: nufi-box restore $_out"
}

backup_restore() {
  _from="${1:?nufi-box restore <directory>}"
  [ -d "$_from" ] || die "no such backup: $_from"
  [ -f "$_from/MANIFEST" ] || die "$_from does not look like a backup (no MANIFEST)"

  if [ "${BACKUP_YES:-0}" != 1 ] && [ "$DRY" != 1 ]; then
    echo "This replaces the databases, the drives and the secrets of the box in"
    echo "$HERE with the contents of:"
    echo
    sed 's/^/  /' "$_from/MANIFEST"
    echo
    printf 'Type the box name (%s) to continue: ' "${BOX_NAME:-nufi}"
    read -r _answer
    [ "$_answer" = "${BOX_NAME:-nufi}" ] || die "not confirmed; nothing was changed"
  fi

  # .env first and before anything is started: the secrets decide what the
  # containers come up as, and restoring data into a stack that is running on
  # the wrong keys is how a restore half-works.
  echo "Restoring $_from"
  run cp "$_from/env" "$ENVF"
  run sh -c "tar -xzf '$_from/ca.tar.gz' -C '${NUFI_DATA_DIR}'"
  # Replace, not merge. `tar -xzf` over the existing tree writes what is in the
  # archive and removes nothing, so a file added since the backup survives a
  # "restore" -- which is the one thing a restore is supposed to undo. The old
  # tree is moved aside rather than deleted: if this is the wrong backup, the
  # department's documents are still in data/drives.previous.
  echo "  drives (the tree as it was is kept in drives.previous)"
  run sh -c "set -e; D='${NUFI_DATA_DIR}'; \
    rm -rf \"\$D/drives.restoring\" \"\$D/drives.previous\"; \
    mkdir -p \"\$D/drives.restoring\"; \
    tar -xzf '$_from/drives.tar.gz' -C \"\$D/drives.restoring\"; \
    if [ -d \"\$D/drives\" ]; then mv \"\$D/drives\" \"\$D/drives.previous\"; fi; \
    mv \"\$D/drives.restoring/drives\" \"\$D/drives\"; \
    rmdir \"\$D/drives.restoring\""

  echo "  stopping the box"
  run $COMPOSE down

  for _vol in app-uploads studio-data caddy-data ingest-state cron-state; do
    [ -f "$_from/$_vol.tar.gz" ] || { echo "  $_vol (not in this backup)"; continue; }
    echo "  $_vol"
    run sh -c "docker run --rm -v 'nufi-box_$_vol:/v' -v '$_from:/in:ro' alpine:3.20 sh -c 'rm -rf /v/* /v/..?* 2>/dev/null; tar -xzf /in/$_vol.tar.gz -C /v'"
  done

  # Only the databases: nothing else may hold a connection while the dump drops
  # and recreates them.
  echo "  starting the databases"
  run $COMPOSE up -d postgres mongodb
  run sh -c "until $COMPOSE exec -T postgres pg_isready -U '${POSTGRES_USER:-nufi}' >/dev/null 2>&1; do sleep 2; done"

  echo "  postgres"
  run sh -c "gzip -dc '$_from/postgres.sql.gz' | $COMPOSE exec -T postgres psql -U '${POSTGRES_USER:-nufi}' -d postgres"
  echo "  mongodb"
  run sh -c "$COMPOSE exec -T mongodb mongorestore --archive --gzip --drop \
    --username '${MONGO_USER:-nufi}' --password '${MONGO_PASSWORD:-}' \
    --authenticationDatabase admin < '$_from/mongodb.archive.gz'"

  echo "  starting the rest"
  run $COMPOSE up -d
  echo
  echo "Restored. Check it with: nufi-box doctor"
}

# --- nightly --------------------------------------------------------------
#
# The box's own scheduler runs Studio flows, not shell, and giving a container
# the docker socket so it can back the box up would hand anything that gets into
# that container the whole host. So the timer belongs to the host, and this
# writes the one the host uses.

_plist_path() { echo "$HOME/Library/LaunchAgents/me.nufi.box.backup.plist"; }
_timer_dir() { echo "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"; }

backup_install_nightly() {
  _at="${BACKUP_AT:-03:30}"
  _hour="${_at%%:*}"; _minute="${_at##*:}"
  case "$OS" in
    Darwin)
      _p="$(_plist_path)"
      echo "Installing a launchd job at $_at: $_p"
      run mkdir -p "$(dirname "$_p")"
      run sh -c "cat > '$_p' <<EOF
<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
  <key>Label</key><string>me.nufi.box.backup</string>
  <key>ProgramArguments</key><array>
    <string>$HERE/nufi-box</string><string>backup</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>$_hour</integer><key>Minute</key><integer>$_minute</integer>
  </dict>
  <key>StandardOutPath</key><string>${NUFI_DATA_DIR}/backup/nightly.log</string>
  <key>StandardErrorPath</key><string>${NUFI_DATA_DIR}/backup/nightly.log</string>
</dict></plist>
EOF"
      run mkdir -p "${NUFI_DATA_DIR}/backup"
      run launchctl unload "$_p"
      run launchctl load "$_p"
      ;;
    Linux)
      _d="$(_timer_dir)"
      echo "Installing a systemd user timer at $_at: $_d"
      run mkdir -p "$_d"
      run sh -c "cat > '$_d/nufi-box-backup.service' <<EOF
[Unit]
Description=NuFi box backup
[Service]
Type=oneshot
ExecStart=$HERE/nufi-box backup
EOF"
      run sh -c "cat > '$_d/nufi-box-backup.timer' <<EOF
[Unit]
Description=NuFi box backup, nightly
[Timer]
OnCalendar=*-*-* $_hour:$_minute:00
Persistent=true
[Install]
WantedBy=timers.target
EOF"
      run systemctl --user daemon-reload
      run systemctl --user enable --now nufi-box-backup.timer
      ;;
    *) die "no nightly backup for $OS" ;;
  esac
  echo "Nightly backup installed. Remove it with: nufi-box backup --remove-nightly"
}

backup_remove_nightly() {
  case "$OS" in
    Darwin)
      _p="$(_plist_path)"
      run launchctl unload "$_p"
      run rm -f "$_p" ;;
    Linux)
      run systemctl --user disable --now nufi-box-backup.timer
      run rm -f "$(_timer_dir)/nufi-box-backup.timer" "$(_timer_dir)/nufi-box-backup.service"
      run systemctl --user daemon-reload ;;
    *) die "no nightly backup for $OS" ;;
  esac
  echo "Nightly backup removed."
}
