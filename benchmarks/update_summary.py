#!/usr/bin/env python3
"""Update benchmarks/SUMMARY.md with Python and Criterion benchmark results."""
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_FILE = os.path.join(SCRIPT_DIR, "performance_results.json")
CRITERION_DIR = os.path.join(ROOT_DIR, "target", "criterion")
SUMMARY_FILE = os.path.join(SCRIPT_DIR, "SUMMARY.md")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "history.json")

# Python benchmark keys
PY_FORMATS = ["mp3", "flac", "ogg", "mp4", "auto_detect",
              "batch_mp3", "batch_flac", "batch_ogg", "batch_mp4", "batch_auto_detect"]

PY_LABELS = {
    "mp3": "MP3", "flac": "FLAC", "ogg": "OGG", "mp4": "MP4",
    "auto_detect": "Auto", "batch_mp3": "B.MP3", "batch_flac": "B.FLAC",
    "batch_ogg": "B.OGG", "batch_mp4": "B.MP4", "batch_auto_detect": "B.Auto",
}

# Criterion benchmark groups
CRITERION_GROUPS = [
    "mp3_small", "mp3_large", "flac_small", "flac_large",
    "ogg_small", "ogg_large", "mp4_small", "mp4_large",
]

CRIT_LABELS = {
    "mp3_small": "MP3s", "mp3_large": "MP3L",
    "flac_small": "FLACs", "flac_large": "FLACL",
    "ogg_small": "OGGs", "ogg_large": "OGGL",
    "mp4_small": "MP4s", "mp4_large": "MP4L",
}


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def read_criterion_results():
    """Read criterion estimates and compute mutagen_rs time, lofty time, and ratio."""
    results = {}
    for group in CRITERION_GROUPS:
        mutagen_est = os.path.join(CRITERION_DIR, group, "mutagen_rs", "new", "estimates.json")
        lofty_est = os.path.join(CRITERION_DIR, group, "lofty", "new", "estimates.json")
        if not os.path.exists(mutagen_est) or not os.path.exists(lofty_est):
            continue
        with open(mutagen_est) as f:
            m = json.load(f)
        with open(lofty_est) as f:
            l = json.load(f)
        m_ns = m["mean"]["point_estimate"]
        l_ns = l["mean"]["point_estimate"]
        ratio = l_ns / m_ns if m_ns > 0 else 0
        results[group] = {
            "mutagen_rs_ns": round(m_ns, 1),
            "lofty_ns": round(l_ns, 1),
            "ratio": round(ratio, 2),
        }
    return results


def fmt_ns(ns):
    """Format nanoseconds to human-readable."""
    if ns >= 1_000_000:
        return f"{ns / 1_000_000:.2f}ms"
    elif ns >= 1_000:
        return f"{ns / 1_000:.2f}us"
    else:
        return f"{ns:.0f}ns"


def fmt_cell(val, prev_val, target=None):
    """Format a speedup cell with optional delta from previous run."""
    if val is None:
        return "-"
    if prev_val is not None:
        delta = val - prev_val
        if delta > 0:
            cell = f"{val}x (+{delta:.1f})"
        elif delta < 0:
            cell = f"{val}x ({delta:.1f})"
        else:
            cell = f"{val}x (=)"
    else:
        cell = f"{val}x"

    if target and val >= target:
        cell = f"**{cell}**"
    return cell


def main():
    timestamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Read Python results
    with open(RESULTS_FILE) as f:
        py_results = json.load(f)

    # Read Criterion results
    crit_results = read_criterion_results()

    # Build entry
    entry = {"timestamp": timestamp}
    for fmt in PY_FORMATS:
        if fmt in py_results:
            entry[f"py_{fmt}"] = round(py_results[fmt]["speedup"], 1)
    for group in CRITERION_GROUPS:
        if group in crit_results:
            entry[f"crit_{group}_ratio"] = crit_results[group]["ratio"]
            entry[f"crit_{group}_mutagen_ns"] = crit_results[group]["mutagen_rs_ns"]
            entry[f"crit_{group}_lofty_ns"] = crit_results[group]["lofty_ns"]

    # Load history, append, save
    history = load_history()
    history.append(entry)
    save_history(history)

    # ---- Generate SUMMARY.md ----
    lines = []
    lines.append("# Benchmark History")
    lines.append("")

    # == Section 1: Python (mutagen_rs vs mutagen) ==
    lines.append("## Python: mutagen_rs vs mutagen")
    lines.append("")
    lines.append("Speedup over Python mutagen (higher = better). Target: **100x**")
    lines.append("")

    cols = ["Run"] + [PY_LABELS[f] for f in PY_FORMATS]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")

    for i, run in enumerate(history):
        prev = history[i - 1] if i > 0 else None
        cells = [f"`{run['timestamp']}`"]
        for fmt in PY_FORMATS:
            key = f"py_{fmt}"
            val = run.get(key)
            prev_val = prev.get(key) if prev else None
            cells.append(fmt_cell(val, prev_val, target=100))
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")

    # == Section 2: Criterion (mutagen_rs vs lofty) ==
    lines.append("## Rust Criterion: mutagen_rs vs lofty-rs")
    lines.append("")
    lines.append("Ratio = lofty_time / mutagen_rs_time (higher = mutagen_rs is faster)")
    lines.append("")

    cols = ["Run"] + [CRIT_LABELS[g] for g in CRITERION_GROUPS]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")

    for i, run in enumerate(history):
        prev = history[i - 1] if i > 0 else None
        cells = [f"`{run['timestamp']}`"]
        for group in CRITERION_GROUPS:
            key = f"crit_{group}_ratio"
            val = run.get(key)
            prev_val = prev.get(key) if prev else None
            cells.append(fmt_cell(val, prev_val))
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")

    # == Criterion absolute times (latest only) ==
    latest = history[-1]
    lines.append("### Latest Criterion times")
    lines.append("")
    lines.append("| Benchmark | mutagen_rs | lofty | Ratio |")
    lines.append("| --- | --- | --- | --- |")
    for group in CRITERION_GROUPS:
        m_key = f"crit_{group}_mutagen_ns"
        l_key = f"crit_{group}_lofty_ns"
        r_key = f"crit_{group}_ratio"
        m = latest.get(m_key)
        l = latest.get(l_key)
        r = latest.get(r_key)
        if m is None:
            continue
        lines.append(f"| {group} | {fmt_ns(m)} | {fmt_ns(l)} | **{r}x** |")

    lines.append("")

    # == Summary ==
    lines.append("## Summary")
    lines.append("")
    py_passed = sum(1 for f in PY_FORMATS if (latest.get(f"py_{f}") or 0) >= 100)
    py_total = sum(1 for f in PY_FORMATS if latest.get(f"py_{f}") is not None)
    crit_faster = sum(1 for g in CRITERION_GROUPS if (latest.get(f"crit_{g}_ratio") or 0) > 1)
    crit_total = sum(1 for g in CRITERION_GROUPS if latest.get(f"crit_{g}_ratio") is not None)
    lines.append(f"- **Date**: {latest['timestamp']}")
    lines.append(f"- **Python benchmarks >= 100x**: {py_passed}/{py_total}")
    lines.append(f"- **Criterion faster than lofty**: {crit_faster}/{crit_total}")

    if len(history) >= 2:
        prev = history[-2]
        changes = []
        for fmt in PY_FORMATS:
            key = f"py_{fmt}"
            cur, old = latest.get(key), prev.get(key)
            if cur is not None and old is not None and cur != old:
                delta = cur - old
                sign = "+" if delta > 0 else ""
                changes.append(f"- {PY_LABELS[fmt]}: {old}x -> {cur}x ({sign}{delta:.1f})")
        for group in CRITERION_GROUPS:
            key = f"crit_{group}_ratio"
            cur, old = latest.get(key), prev.get(key)
            if cur is not None and old is not None and cur != old:
                delta = cur - old
                sign = "+" if delta > 0 else ""
                changes.append(f"- {group} (vs lofty): {old}x -> {cur}x ({sign}{delta:.2f})")
        if changes:
            lines.append("")
            lines.append("### Changes from previous run")
            lines.append("")
            lines.extend(changes)

    lines.append("")
    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(lines))

    print(f"Summary updated: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
