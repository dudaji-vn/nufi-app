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
print(f"{'NAME':<20} {'WHEN':<16} {'DRIVE':<10} NEXT")
for s in schedules:
    nxt = ""
    when = now
    for _ in range(60 * 24 * 366):
        when += datetime.timedelta(minutes=1)
        if s.cron.matches(when):
            nxt = when.strftime("%Y-%m-%d %H:%M")
            break
    print(f"{s.name:<20} {s.cron.text:<16} {s.drive:<10} {nxt or 'never'}")
    print(f"{'':<20} -> {s.drive}/_routines/{s.filename(now)}")
PY
}
