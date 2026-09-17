# `nufi-box schedule list` — what the scheduler will do, read with the
# scheduler's own parser.
#
# Deliberately not a second reader of schedules.ini written in shell: a CLI that
# parses the file its own way can disagree with the daemon about what is going
# to run, and the whole value of this command is that it cannot.
schedule_list() {
  _dir="$(dirname "$HERE")/platform/adapters/nufi-cron"
  [ -f "$_dir/nufi_cron.py" ] || die "nufi-cron is not in this checkout: $_dir"
  run python3 - "$_dir" "${NUFI_DATA_DIR}/schedules.ini" <<'PY'
import datetime, pathlib, sys
sys.path.insert(0, sys.argv[1])
import nufi_cron

path = pathlib.Path(sys.argv[2])
schedules, problems = nufi_cron.load_schedules(path)
for problem in problems:
    print(f"  problem  {problem}")
if not schedules:
    print(f"No schedules in {path}." if not problems else "")
    print("A schedule is a section in that file; see deploy/box/README.md.")
    sys.exit(0)

now = datetime.datetime.now().replace(second=0, microsecond=0)
rows = []
for s in schedules:
    if s.cron is not None:
        when_col = s.cron.text
        nxt = ""
        when = now
        for _ in range(60 * 24 * 366):
            when += datetime.timedelta(minutes=1)
            if s.cron.matches(when):
                nxt = when.strftime("%Y-%m-%d %H:%M")
                break
        next_col = nxt or "never"
    else:
        when_col = f"on file in {s.watch}/"
        next_col = "(next file)"
    rows.append((s, when_col, next_col))

# "on file in <folder>/" runs longer than any cron expression this file
# accepts, so a fixed width truncated it; sized from the longest WHEN
# actually in this schedules.ini instead.
when_width = max([len("WHEN")] + [len(when_col) for _, when_col, _ in rows])
print(f"{'NAME':<20} {'WHEN':<{when_width}} {'DRIVE':<10} NEXT")
for s, when_col, next_col in rows:
    print(f"{s.name:<20} {when_col:<{when_width}} {s.drive:<10} {next_col}")
    # `s.filename(now)` -- no file passed -- leaves {file} as literal text;
    # this line is a preview of the pattern, not a run.
    print(f"{'':<20} -> {s.drive}/_routines/{s.filename(now)}")
PY
}
