"""``nufi-egress report coverage-map`` — PII entity coverage map (patch166).

Scans a directory and builds a matrix: file x entity_type, showing which files
contain which types of PII. Useful for understanding PII exposure surface area.

Formats: text (default), json, csv.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def build_coverage_map(
    target: str | Path,
    *,
    patterns: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Scan *target* and build a file x entity_type coverage matrix.

    Returns a dict with:
      - entity_types: sorted list of all entity types found
      - files: sorted list of files with findings
      - matrix: dict[file][entity_type] -> count
      - summary: per-entity-type total counts
      - total_files_scanned: int
      - total_files_with_pii: int
    """
    from enforcement.scan_cmd import scan_path

    result = scan_path(target, patterns=patterns, exclude=exclude)

    # Build matrix: file -> entity_type -> count
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    entity_types: Set[str] = set()

    for finding in result.findings:
        if not finding.finding_type.startswith("PII:"):
            continue
        entity = finding.finding_type.split(":", 1)[1]
        matrix[finding.file][entity] += 1
        entity_types.add(entity)

    sorted_types = sorted(entity_types)
    sorted_files = sorted(matrix.keys())

    # Summary: total counts per entity type
    summary: Dict[str, int] = {}
    for et in sorted_types:
        summary[et] = sum(matrix[f].get(et, 0) for f in sorted_files)

    return {
        "entity_types": sorted_types,
        "files": sorted_files,
        "matrix": {f: dict(matrix[f]) for f in sorted_files},
        "summary": summary,
        "total_files_scanned": result.files_scanned,
        "total_files_with_pii": len(sorted_files),
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_text(data: Dict[str, Any]) -> str:
    """Render coverage map as aligned text table."""
    entity_types = data["entity_types"]
    files = data["files"]
    matrix = data["matrix"]

    if not files:
        return "No PII findings detected.\n"

    lines: List[str] = []

    # Header
    lines.append(f"PII Coverage Map — {data['total_files_with_pii']} files, "
                 f"{len(entity_types)} entity types\n")

    # Compute column widths
    file_col_width = max(len("File"), max(len(f) for f in files))
    col_widths = [max(len(et), 5) for et in entity_types]

    # Header row
    header = f"{'File':<{file_col_width}}"
    for i, et in enumerate(entity_types):
        header += f"  {et:>{col_widths[i]}}"
    lines.append(header)
    lines.append("-" * len(header))

    # Data rows
    for f in files:
        row = f"{f:<{file_col_width}}"
        for i, et in enumerate(entity_types):
            count = matrix[f].get(et, 0)
            cell = str(count) if count else "."
            row += f"  {cell:>{col_widths[i]}}"
        lines.append(row)

    # Summary row
    lines.append("-" * len(header))
    summary_row = f"{'TOTAL':<{file_col_width}}"
    for i, et in enumerate(entity_types):
        summary_row += f"  {data['summary'][et]:>{col_widths[i]}}"
    lines.append(summary_row)
    lines.append("")

    return "\n".join(lines)


def render_json(data: Dict[str, Any]) -> str:
    """Render coverage map as JSON."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_csv(data: Dict[str, Any]) -> str:
    """Render coverage map as CSV."""
    entity_types = data["entity_types"]
    files = data["files"]
    matrix = data["matrix"]

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["file"] + entity_types)

    # Data rows
    for f in files:
        row = [f] + [str(matrix[f].get(et, 0)) for et in entity_types]
        writer.writerow(row)

    return output.getvalue()


def render(data: Dict[str, Any], fmt: str = "text") -> str:
    """Render coverage map in the specified format."""
    if fmt == "json":
        return render_json(data)
    if fmt == "csv":
        return render_csv(data)
    return render_text(data)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_report_coverage_map(args) -> int:
    """CLI handler for ``nufi-egress report coverage-map``."""
    target = getattr(args, "directory", ".")
    patterns = None
    if getattr(args, "pattern", None):
        patterns = [p.strip() for p in args.pattern.split(",")]
    exclude = None
    if getattr(args, "exclude", None):
        exclude = [p.strip() for p in args.exclude.split(",")]

    fmt = getattr(args, "format", "text")
    output_path = getattr(args, "output", None)

    data = build_coverage_map(target, patterns=patterns, exclude=exclude)
    rendered = render(data, fmt)

    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
        print(f"[coverage-map] written: {output_path}", file=sys.stderr)
    else:
        print(rendered, end="")

    return 0
