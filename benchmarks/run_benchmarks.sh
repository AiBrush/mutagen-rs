#!/usr/bin/env bash
set -euo pipefail

source ~/.venv/ai3.14/bin/activate
source ~/.cargo/env

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BENCH_DIR="$SCRIPT_DIR"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
OUTFILE="$BENCH_DIR/benchmark_${TIMESTAMP}.txt"

{
    echo "=========================================="
    echo "  Benchmark Run: $(date)"
    echo "=========================================="
    echo ""

    # 1. Build
    echo ">>> Building mutagen_rs (release)..."
    maturin develop --release 2>&1 | tail -3
    echo ""

    # 2. Python benchmarks: mutagen_rs vs mutagen
    echo "=========================================="
    echo "  Python: mutagen_rs vs mutagen"
    echo "=========================================="
    echo ""
    python "$ROOT_DIR/tests/test_performance.py" 2>&1 || true
    echo ""

    # 3. Rust criterion benchmarks: mutagen_rs vs lofty
    echo "=========================================="
    echo "  Rust Criterion: mutagen_rs vs lofty-rs"
    echo "=========================================="
    echo ""
    cargo bench --bench parse_comparison 2>&1 | grep -E '(Benchmarking|time:|change:)' || true
    echo ""

    echo "=========================================="
    echo "  Done: $(date)"
    echo "=========================================="
} | tee "$OUTFILE"

# Update the running summary
python "$BENCH_DIR/update_summary.py" "$TIMESTAMP"

echo ""
echo "Results saved to: $OUTFILE"
echo "Summary updated:  $BENCH_DIR/SUMMARY.md"
