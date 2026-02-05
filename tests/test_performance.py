"""Performance benchmark: mutagen_rs vs original mutagen.

Benchmark fairness notes:
- Both sides read from disk each iteration (clear_cache() clears Rust's in-memory file cache).
  OS page cache benefits both sides equally.
- Single-file: Both sides fully parse tags + info. Rust uses _fast_read() returning a flat dict;
  original uses cls(p) constructor. Both iterate all tag keys/values.
- Batch: Both sides fully parse tags + info and iterate results.
  Rust uses rayon-based _rust_batch_open() (multi-core parallelism) vs sequential original.
  Parallelism advantage is disclosed but legitimate — it's a real architectural benefit.
"""
import json
import time
import os
import sys

import mutagen
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

import mutagen_rs

TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_files")
ITERATIONS = 200


def find_test_files():
    files = {}
    for f in os.listdir(TEST_DIR):
        path = os.path.join(TEST_DIR, f)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext == ".mp3":
            files.setdefault("mp3", []).append(path)
        elif ext == ".flac":
            files.setdefault("flac", []).append(path)
        elif ext == ".ogg":
            files.setdefault("ogg", []).append(path)
        elif ext in (".m4a", ".m4b", ".mp4"):
            files.setdefault("mp4", []).append(path)
    return files


def benchmark_original(name, cls, paths, iterations=ITERATIONS, iterate_tags=True):
    """Benchmark original mutagen: open file, access info, iterate all tags."""
    if not paths:
        return None

    # Warm up
    for p in paths:
        try:
            cls(p)
        except Exception:
            pass

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for p in paths:
            try:
                f = cls(p)
                if hasattr(f, 'info') and f.info:
                    _ = f.info.length
                if iterate_tags and f.tags:
                    for k in f.tags.keys():
                        _ = f.tags[k]
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return min(times)


def benchmark_rust(name, paths, iterations=ITERATIONS):
    """Benchmark Rust _fast_read: open file, parse all tags + info, iterate results.

    _fast_read() returns a flat Python dict with info fields and all tags.
    We iterate all keys/values to match the work done by the original benchmark.
    clear_cache() is called each iteration to force fresh disk reads.
    """
    if not paths:
        return None

    # Warm up
    for p in paths:
        try:
            mutagen_rs._fast_read(p)
        except Exception:
            pass

    times = []
    for _ in range(iterations):
        mutagen_rs.clear_cache()
        start = time.perf_counter()
        for p in paths:
            try:
                d = mutagen_rs._fast_read(p)
                # Iterate all keys/values to match original's tag iteration
                for k in d:
                    _ = d[k]
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return min(times)


def main():
    files = find_test_files()
    print(f"Test files: { {k: len(v) for k, v in files.items()} }")
    print(f"Iterations: {ITERATIONS}")
    print()
    print("Benchmark methodology:")
    print("  Single-file: full parse (tags + info) + iterate all keys/values")
    print("    Original: cls(p) + info.length + iterate tags")
    print("    Rust:     _fast_read(p) + iterate all dict keys/values")
    print("    Both read from disk each iteration (Rust cache cleared)")
    print("  Batch: full parse + iterate results")
    print("    Original: sequential cls(p) + iterate tags")
    print("    Rust:     rayon parallel _rust_batch_open() + iterate all results")
    print()

    format_map = [
        ("mp3", MP3, "MP3"),
        ("flac", FLAC, "FLAC"),
        ("ogg", OggVorbis, "OggVorbis"),
        ("mp4", MP4, "MP4"),
    ]

    results = {}
    all_passed = True

    for name, orig_cls, rust_cls_name in format_map:
        paths = files.get(name, [])
        if not paths:
            continue

        # Filter to only files that both can handle
        valid_paths = []
        for p in paths:
            try:
                orig_cls(p)
                mutagen_rs._fast_read(p)
                valid_paths.append(p)
            except Exception:
                pass

        if not valid_paths:
            print(f"{name}: no files both implementations can handle")
            continue

        print(f"Benchmarking {name} ({len(valid_paths)} files)...")

        orig_time = benchmark_original(name, orig_cls, valid_paths, iterate_tags=True)
        rust_time = benchmark_rust(name, valid_paths)

        speedup = orig_time / rust_time if rust_time > 0 else float('inf')

        orig_per_file = (orig_time / len(valid_paths)) * 1000
        rust_per_file = (rust_time / len(valid_paths)) * 1000

        passed = speedup >= 100.0

        results[name] = {
            "files": len(valid_paths),
            "original_ms_per_file": orig_per_file,
            "rust_ms_per_file": rust_per_file,
            "speedup": speedup,
            "passed": passed,
        }

        status = "PASS" if passed else "FAIL"
        print(f"  Original: {orig_per_file:.4f} ms/file")
        print(f"  Rust:     {rust_per_file:.4f} ms/file")
        print(f"  Speedup:  {speedup:.1f}x [{status}]")
        print()

        if not passed:
            all_passed = False

    # Auto-detect benchmark
    all_paths = []
    for ps in files.values():
        all_paths.extend(ps)

    valid_auto = []
    for p in all_paths:
        try:
            mutagen.File(p)
            mutagen_rs._fast_read(p)
            valid_auto.append(p)
        except Exception:
            pass

    if valid_auto:
        print(f"Benchmarking auto-detect ({len(valid_auto)} files)...")

        # Original
        times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            for p in valid_auto:
                try:
                    f = mutagen.File(p)
                    if f and hasattr(f, 'info') and f.info:
                        _ = f.info.length
                    if f and f.tags:
                        for k in f.tags.keys():
                            _ = f.tags[k]
                except Exception:
                    pass
            times.append(time.perf_counter() - start)
        orig_time = min(times)

        # Rust
        times = []
        for _ in range(ITERATIONS):
            mutagen_rs.clear_cache()
            start = time.perf_counter()
            for p in valid_auto:
                try:
                    d = mutagen_rs._fast_read(p)
                    for k in d:
                        _ = d[k]
                except Exception:
                    pass
            times.append(time.perf_counter() - start)
        rust_time = min(times)

        speedup = orig_time / rust_time if rust_time > 0 else float('inf')
        passed = speedup >= 100.0
        results["auto_detect"] = {
            "files": len(valid_auto),
            "original_ms_per_file": (orig_time / len(valid_auto)) * 1000,
            "rust_ms_per_file": (rust_time / len(valid_auto)) * 1000,
            "speedup": speedup,
            "passed": passed,
        }

        status = "PASS" if passed else "FAIL"
        print(f"  Original: {(orig_time / len(valid_auto)) * 1000:.4f} ms/file")
        print(f"  Rust:     {(rust_time / len(valid_auto)) * 1000:.4f} ms/file")
        print(f"  Speedup:  {speedup:.1f}x [{status}]")

        if not passed:
            all_passed = False

    # Batch API benchmark with real unique file copies
    import shutil
    import tempfile

    batch_dir = tempfile.mkdtemp(prefix="mutagen_batch_")
    BATCH_COPIES = 40  # Create 40 copies of each file for batch parallelism

    try:
        # Create unique copies for realistic batch testing
        batch_paths = {}  # {format: [paths]}
        batch_all = []
        for name_key in ["mp3", "flac", "ogg", "mp4"]:
            paths = files.get(name_key, [])
            valid_paths = []
            for p in paths:
                try:
                    if name_key == "mp3": MP3(p)
                    elif name_key == "flac": FLAC(p)
                    elif name_key == "ogg": OggVorbis(p)
                    elif name_key == "mp4": MP4(p)
                    valid_paths.append(p)
                except Exception:
                    pass

            copied = []
            for i in range(BATCH_COPIES):
                for p in valid_paths:
                    base = os.path.basename(p)
                    dest = os.path.join(batch_dir, f"copy{i}_{base}")
                    if not os.path.exists(dest):
                        shutil.copy2(p, dest)
                    copied.append(dest)
            batch_paths[name_key] = copied
            batch_all.extend(copied)

        # Warm the OS file cache
        for p in batch_all[:100]:
            with open(p, "rb") as f:
                f.read()

        print(f"\n{'='*60}")
        print(f"BATCH API BENCHMARK (Rust: rayon parallel, Original: sequential)")
        print(f"Both sides: full parse + iterate all tags. {BATCH_COPIES} copies per file.")
        print(f"{'='*60}\n")

        format_cls = {"mp3": MP3, "flac": FLAC, "ogg": OggVorbis, "mp4": MP4}

        for name_key, orig_cls in format_cls.items():
            paths = batch_paths.get(name_key, [])
            if not paths:
                continue

            n_files = len(paths)
            iters = max(20, ITERATIONS // 2)
            print(f"Batch {name_key} ({n_files} unique files)...")

            # Original: sequential with full tag access
            orig_time = benchmark_original(name_key, orig_cls, paths, iters)

            # Rust batch: parse + iterate all results to force Python object creation
            for _ in range(5):
                mutagen_rs._rust_batch_open(paths)

            times = []
            for _ in range(iters):
                mutagen_rs.clear_cache()
                start = time.perf_counter()
                result = mutagen_rs._rust_batch_open(paths)
                # Iterate all results to force tag materialization to Python objects
                for key in result.keys():
                    d = result[key]
                    for tag_key in d:
                        _ = d[tag_key]
                times.append(time.perf_counter() - start)
            batch_time = min(times)

            speedup = orig_time / batch_time if batch_time > 0 else float('inf')
            passed = speedup >= 100.0

            results[f"batch_{name_key}"] = {
                "files": n_files,
                "original_ms_per_file": (orig_time / n_files) * 1000,
                "rust_batch_ms_per_file": (batch_time / n_files) * 1000,
                "speedup": speedup,
                "passed": passed,
            }

            status = "PASS" if passed else "FAIL"
            print(f"  Original:    {(orig_time / n_files) * 1000:.4f} ms/file")
            print(f"  Rust batch:  {(batch_time / n_files) * 1000:.4f} ms/file  {speedup:.1f}x [{status}]")
            print()

            if not passed:
                all_passed = False

        # Batch all files
        if batch_all:
            n_auto = len(batch_all)
            iters = max(20, ITERATIONS // 2)
            print(f"Batch auto-detect ({n_auto} unique files)...")

            # Original sequential with full tag access
            times = []
            for _ in range(iters):
                start = time.perf_counter()
                for p in batch_all:
                    try:
                        f = mutagen.File(p)
                        if f and hasattr(f, 'info') and f.info:
                            _ = f.info.length
                        if f and f.tags:
                            for k in f.tags.keys():
                                _ = f.tags[k]
                    except Exception:
                        pass
                times.append(time.perf_counter() - start)
            orig_time = min(times)

            # Rust batch: parse + iterate all results
            for _ in range(5):
                mutagen_rs._rust_batch_open(batch_all)
            times = []
            for _ in range(iters):
                mutagen_rs.clear_cache()
                start = time.perf_counter()
                result = mutagen_rs._rust_batch_open(batch_all)
                for key in result.keys():
                    d = result[key]
                    for tag_key in d:
                        _ = d[tag_key]
                times.append(time.perf_counter() - start)
            batch_time = min(times)

            speedup = orig_time / batch_time if batch_time > 0 else float('inf')
            passed = speedup >= 100.0

            results["batch_auto_detect"] = {
                "files": n_auto,
                "original_ms_per_file": (orig_time / n_auto) * 1000,
                "rust_batch_ms_per_file": (batch_time / n_auto) * 1000,
                "speedup": speedup,
                "passed": passed,
            }

            status = "PASS" if passed else "FAIL"
            print(f"  Original:    {(orig_time / n_auto) * 1000:.4f} ms/file")
            print(f"  Rust batch:  {(batch_time / n_auto) * 1000:.4f} ms/file  {speedup:.1f}x [{status}]")

            if not passed:
                all_passed = False

    finally:
        shutil.rmtree(batch_dir, ignore_errors=True)

    # Save results
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "performance_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    if all_passed:
        print("ALL BENCHMARKS PASSED (>=100x speedup)")
    else:
        print("SOME BENCHMARKS BELOW 100x TARGET")
    print(f"Results saved to {output_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
