"""Injection detection benchmark — recall/precision/F1 측정.

실행: python3 scripts/bench_injection.py [--json-out FILE] [--markdown]

목표: recall >= 0.95, precision >= 0.95, benign FP rate <= 0.05
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit.detectors.prompt_injection import PromptInjectionDetector  # noqa: E402

GOLD_PATH = ROOT / "samples" / "injection_gold.jsonl"
JSON_OUT_DEFAULT = ROOT / "docs" / "reports" / "injection-benchmark.json"


def load_gold():
    """Load the gold set."""
    samples = []
    with open(GOLD_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def run_benchmark():
    """Run the benchmark and return metrics."""
    detector = PromptInjectionDetector(min_severity="low")
    samples = load_gold()

    # Counters
    tp = 0  # injection correctly detected
    fn = 0  # injection missed
    fp = 0  # benign incorrectly flagged
    tn = 0  # benign correctly passed

    results = []
    severity_stats: dict[str, dict[str, int]] = {}  # severity -> {tp, fn}

    for sample in samples:
        text = sample["text"]
        label = sample["label"]
        severity = sample.get("severity")
        detected = detector.is_injection(text)

        if label == "injection":
            if severity:
                s = severity_stats.setdefault(severity, {"tp": 0, "fn": 0})
                if detected:
                    s["tp"] += 1
                else:
                    s["fn"] += 1
            if detected:
                tp += 1
                results.append(("TP", label, severity, text[:60]))
            else:
                fn += 1
                results.append(("FN", label, severity, text[:60]))
        else:  # benign
            if detected:
                fp += 1
                results.append(("FP", label, severity, text[:60]))
            else:
                tn += 1
                results.append(("TN", label, severity, text[:60]))

    # Metrics
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    total_benign = fp + tn
    benign_fp_rate = fp / total_benign if total_benign > 0 else 0.0

    # Per-severity recall
    severity_summary = {}
    for sev, counts in sorted(severity_stats.items()):
        total = counts["tp"] + counts["fn"]
        sev_recall = counts["tp"] / total if total > 0 else 0.0
        severity_summary[sev] = {
            "tp": counts["tp"],
            "fn": counts["fn"],
            "total": total,
            "recall": round(sev_recall, 4),
        }

    return {
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "benign_fp_rate": benign_fp_rate,
        "total_samples": len(samples),
        "total_injection": tp + fn,
        "total_benign": total_benign,
        "severity": severity_summary,
        "results": results,
    }


def render_json(metrics: dict) -> dict:
    """Return JSON-serialisable report (without per-sample results)."""
    return {
        "benchmark": "injection",
        "total_samples": metrics["total_samples"],
        "total_injection": metrics["total_injection"],
        "total_benign": metrics["total_benign"],
        "tp": metrics["tp"],
        "fn": metrics["fn"],
        "fp": metrics["fp"],
        "tn": metrics["tn"],
        "recall": round(metrics["recall"], 4),
        "precision": round(metrics["precision"], 4),
        "f1": round(metrics["f1"], 4),
        "benign_fp_rate": round(metrics["benign_fp_rate"], 4),
        "severity": metrics["severity"],
    }


def render_markdown(metrics: dict) -> str:
    """Render benchmark results as Markdown."""
    lines = [
        "# Injection Detection Benchmark Report",
        "",
        f"**Gold set**: `samples/injection_gold.jsonl` ({metrics['total_samples']} samples: "
        f"{metrics['total_injection']} injection + {metrics['total_benign']} benign)",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Recall | {metrics['recall']:.4f} |",
        f"| Precision | {metrics['precision']:.4f} |",
        f"| F1 | {metrics['f1']:.4f} |",
        f"| Benign FP rate | {metrics['benign_fp_rate']:.4f} |",
        "",
        "## Confusion Matrix",
        "",
        "| | Predicted Injection | Predicted Benign |",
        "|---|---|---|",
        f"| Actual Injection | TP={metrics['tp']} | FN={metrics['fn']} |",
        f"| Actual Benign | FP={metrics['fp']} | TN={metrics['tn']} |",
        "",
        "## Severity Breakdown",
        "",
        "| Severity | TP | FN | Total | Recall |",
        "|----------|----|----|-------|--------|",
    ]
    for sev, s in sorted(metrics["severity"].items(),
                         key=lambda x: ["critical", "high", "medium", "low"].index(x[0])
                         if x[0] in ["critical", "high", "medium", "low"] else 99):
        lines.append(f"| {sev} | {s['tp']} | {s['fn']} | {s['total']} | {s['recall']:.4f} |")

    # Errors
    errors = [r for r in metrics["results"] if r[0] in ("FN", "FP")]
    if errors:
        lines.extend(["", "## Errors", ""])
        for kind, label, severity, text in errors:
            lines.append(f"- **[{kind}]** ({label}, {severity}) `{text}`")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Injection detection benchmark")
    parser.add_argument("--json-out", type=str, default=None,
                        help="Write JSON report to file (default: docs/reports/injection-benchmark.json)")
    parser.add_argument("--markdown", action="store_true",
                        help="Print Markdown report to stdout")
    parser.add_argument("--no-json", action="store_true",
                        help="Skip writing JSON report")
    args = parser.parse_args()

    metrics = run_benchmark()

    if args.markdown:
        print(render_markdown(metrics))
    else:
        print("=" * 60)
        print("Injection Detection Benchmark Results")
        print("=" * 60)
        print(f"Gold set: {metrics['total_samples']} samples "
              f"({metrics['total_injection']} injection + {metrics['total_benign']} benign)")
        print()
        print(f"{'Metric':<20} {'Value':<10}")
        print("-" * 30)
        print(f"{'True Positives':<20} {metrics['tp']}")
        print(f"{'False Negatives':<20} {metrics['fn']}")
        print(f"{'False Positives':<20} {metrics['fp']}")
        print(f"{'True Negatives':<20} {metrics['tn']}")
        print("-" * 30)
        print(f"{'Recall':<20} {metrics['recall']:.4f}")
        print(f"{'Precision':<20} {metrics['precision']:.4f}")
        print(f"{'F1':<20} {metrics['f1']:.4f}")
        print(f"{'Benign FP rate':<20} {metrics['benign_fp_rate']:.4f}")

        # Severity breakdown
        print()
        print("Severity Breakdown:")
        for sev, s in sorted(metrics["severity"].items(),
                             key=lambda x: ["critical", "high", "medium", "low"].index(x[0])
                             if x[0] in ["critical", "high", "medium", "low"] else 99):
            print(f"  {sev:<10} recall={s['recall']:.4f} (TP={s['tp']} FN={s['fn']} / {s['total']})")

        print("=" * 60)

        # Show errors if any
        errors = [r for r in metrics["results"] if r[0] in ("FN", "FP")]
        if errors:
            print("\nErrors:")
            for kind, label, severity, text in errors:
                print(f"  [{kind}] ({label}, {severity}) {text}")

        # Pass/fail
        passed = metrics["recall"] >= 0.95 and metrics["benign_fp_rate"] <= 0.05
        print(f"\nResult: {'PASS' if passed else 'FAIL'}")
        print(f"  recall >= 0.95: {'OK' if metrics['recall'] >= 0.95 else 'FAIL'}")
        print(f"  benign FP rate <= 0.05: {'OK' if metrics['benign_fp_rate'] <= 0.05 else 'FAIL'}")

    # Write JSON report
    if not args.no_json:
        json_path = Path(args.json_out) if args.json_out else JSON_OUT_DEFAULT
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(render_json(metrics), indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        if not args.markdown:
            print(f"\nJSON report written to: {json_path}")

    sys.exit(0 if (metrics["recall"] >= 0.95 and metrics["benign_fp_rate"] <= 0.05) else 1)


if __name__ == "__main__":
    main()
