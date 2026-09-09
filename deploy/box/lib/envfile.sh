#!/bin/bash
# envfile.sh — helpers for editing a KEY=VALUE .env file in place. bash 3.2
# compatible. Meant to be sourced, not executed.
#
# Both helpers match KEY as a literal string anchored at the start of the
# line (via awk's index(), not a grep regex) so a key containing a
# metacharacter such as "." (e.g. "A.B") can't accidentally match an
# unrelated line (e.g. "AXB=...") the way `grep "^KEY="` would.

# envfile_has FILE KEY — true if FILE contains a line starting with "KEY=".
envfile_has() {
  local file="$1" key="$2"
  [ -f "$file" ] && awk -v k="$key" 'index($0, k "=") == 1 { found = 1 } END { exit !found }' "$file"
}

# envfile_set FILE KEY VALUE — replace the KEY= line if present, else append
# it. VALUE is written verbatim after "KEY=" — the caller is responsible for
# any quoting it wants in the resulting line. Writes via a same-directory
# mktemp + mv so the update is atomic and never crosses a filesystem/device.
envfile_set() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp "$file.XXXXXX")"
  if [ -f "$file" ]; then
    awk -v k="$key" 'index($0, k "=") != 1' "$file" > "$tmp"
  fi
  # Guard against gluing onto an unterminated last line: some filters (and
  # some grep implementations) preserve a source file's missing trailing
  # newline, which would otherwise merge the appended line into the last
  # kept one.
  if [ -s "$tmp" ] && [ "$(tail -c 1 "$tmp" | od -An -c | tr -d ' ')" != '\n' ]; then
    printf '\n' >> "$tmp"
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$file"
}
