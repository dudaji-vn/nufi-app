#!/bin/bash
# envfile.sh — helpers for editing a KEY=VALUE .env file in place. bash 3.2
# compatible. Meant to be sourced, not executed.

# envfile_has FILE KEY — true if FILE contains a KEY= line.
envfile_has() {
  local file="$1" key="$2"
  [ -f "$file" ] && grep -q "^$key=" "$file"
}

# envfile_set FILE KEY VALUE — replace the KEY= line if present, else append
# it. VALUE is written verbatim after "KEY=" — the caller is responsible for
# any quoting it wants in the resulting line. Writes via a same-directory
# mktemp + mv so the update is atomic and never crosses a filesystem/device.
envfile_set() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp "$file.XXXXXX")"
  if [ -f "$file" ]; then
    grep -v "^$key=" "$file" > "$tmp" || true
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$file"
}
