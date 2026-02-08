"""Performance benchmark: mutagen_rs vs original mutagen.

Measures three scenarios:
1. Cold read:  Rust file cache cleared each iteration (both sides read from disk via OS page cache)
2. Warm read:  Rust file cache warm (Rust skips I/O, Python still reads from disk)
3. Batch:      Rust rayon parallel vs Python sequential (cold, unique files)

All scenarios: both sides fully parse tags + info, then iterate all keys/values.
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


def benchmark_rust_cold(name, paths, iterations=ITERATIONS):
    """Benchmark Rust _fast_read with cold cache (cleared each iteration)."""
    if not paths:
        return None
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
                for k in d:
                    _ = d[k]
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return min(times)


def benchmark_rust_warm(name, paths, iterations=ITERATIONS):
    """Benchmark Rust _fast_read with warm cache (no I/O after first pass)."""
    if not paths:
        return None
    # Warm the cache
    mutagen_rs.clear_cache()
    for p in paths:
        try:
            mutagen_rs._fast_read(p)
        except Exception:
            pass
    # Measure with warm cache (no clear_cache)
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for p in paths:
            try:
                d = mutagen_rs._fast_read(p)
                for k in d:
                    _ = d[k]
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return min(times)


def filter_valid_paths(orig_cls, paths):
    valid = []
    for p in paths:
        try:
            orig_cls(p)
            mutagen_rs._fast_read(p)
            valid.append(p)
        except Exception:
            pass
    return valid


def main():
    files = find_test_files()
    print(f"Test files: { {k: len(v) for k, v in files.items()} }")
    print(f"Iterations: {ITERATIONS}")
    print()
    print("Benchmark methodology:")
    print("  Both sides: full parse (tags + info) + iterate all keys/values")
    print("  Cold:  Rust file cache cleared (both read from disk via OS page cache)")
    print("  Warm:  Rust file cache warm (Rust: cache hit, Python: disk read)")
    print("  Batch: Rust rayon parallel vs Python sequential (cold, unique files)")
    print()

    format_map = [
        ("mp3", MP3, "MP3"),
        ("flac", FLAC, "FLAC"),
        ("ogg", OggVorbis, "OggVorbis"),
        ("mp4", MP4, "MP4"),
    ]

    results = {}

    # ---- Single-file benchmarks (cold + warm) ----
    print(f"{'='*60}")
    print(f"SINGLE-FILE BENCHMARKS")
    print(f"{'='*60}\n")

    for name, orig_cls, rust_cls_name in format_map:
        paths = files.get(name, [])
        valid_paths = filter_valid_paths(orig_cls, paths)
        if not valid_paths:
            continue

        print(f"{name.upper()} ({len(valid_paths)} files):")

        orig_time = benchmark_original(name, orig_cls, valid_paths, iterate_tags=True)
        cold_time = benchmark_rust_cold(name, valid_paths)
        warm_time = benchmark_rust_warm(name, valid_paths)

        cold_speedup = orig_time / cold_time if cold_time > 0 else float('inf')
        warm_speedup = orig_time / warm_time if warm_time > 0 else float('inf')

        orig_pf = (orig_time / len(valid_paths)) * 1000
        cold_pf = (cold_time / len(valid_paths)) * 1000
        warm_pf = (warm_time / len(valid_paths)) * 1000

        print(f"  Original:   {orig_pf:.4f} ms/file")
        print(f"  Rust cold:  {cold_pf:.4f} ms/file  ({cold_speedup:.1f}x)")
        print(f"  Rust warm:  {warm_pf:.4f} ms/file  ({warm_speedup:.1f}x)")
        print()

        results[name] = {
            "files": len(valid_paths),
            "original_ms_per_file": orig_pf,
            "rust_cold_ms_per_file": cold_pf,
            "rust_warm_ms_per_file": warm_pf,
            "speedup_cold": cold_speedup,
            "speedup_warm": warm_speedup,
        }

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
        print(f"AUTO-DETECT ({len(valid_auto)} files):")

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

        # Cold
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
        cold_time = min(times)

        # Warm
        mutagen_rs.clear_cache()
        for p in valid_auto:
            try:
                mutagen_rs._fast_read(p)
            except Exception:
                pass
        times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            for p in valid_auto:
                try:
                    d = mutagen_rs._fast_read(p)
                    for k in d:
                        _ = d[k]
                except Exception:
                    pass
            times.append(time.perf_counter() - start)
        warm_time = min(times)

        cold_speedup = orig_time / cold_time if cold_time > 0 else float('inf')
        warm_speedup = orig_time / warm_time if warm_time > 0 else float('inf')

        n = len(valid_auto)
        print(f"  Original:   {(orig_time / n) * 1000:.4f} ms/file")
        print(f"  Rust cold:  {(cold_time / n) * 1000:.4f} ms/file  ({cold_speedup:.1f}x)")
        print(f"  Rust warm:  {(warm_time / n) * 1000:.4f} ms/file  ({warm_speedup:.1f}x)")
        print()

        results["auto_detect"] = {
            "files": n,
            "original_ms_per_file": (orig_time / n) * 1000,
            "rust_cold_ms_per_file": (cold_time / n) * 1000,
            "rust_warm_ms_per_file": (warm_time / n) * 1000,
            "speedup_cold": cold_speedup,
            "speedup_warm": warm_speedup,
        }

    # ---- Batch API benchmark ----
    import shutil
    import tempfile

    batch_dir = tempfile.mkdtemp(prefix="mutagen_batch_")
    BATCH_COPIES = 40

    try:
        batch_paths = {}
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

        # Warm OS file cache
        for p in batch_all[:100]:
            with open(p, "rb") as f:
                f.read()

        print(f"{'='*60}")
        print(f"BATCH BENCHMARK (Rust: rayon parallel, Original: sequential)")
        print(f"Cold cache, {BATCH_COPIES} copies per file, full parse + iterate tags")
        print(f"{'='*60}\n")

        format_cls = {"mp3": MP3, "flac": FLAC, "ogg": OggVorbis, "mp4": MP4}

        for name_key, orig_cls in format_cls.items():
            paths = batch_paths.get(name_key, [])
            if not paths:
                continue
            n_files = len(paths)
            iters = max(20, ITERATIONS // 2)
            print(f"Batch {name_key} ({n_files} files):")

            orig_time = benchmark_original(name_key, orig_cls, paths, iters)

            for _ in range(5):
                mutagen_rs._rust_batch_open(paths)
            times = []
            for _ in range(iters):
                mutagen_rs.clear_cache()
                start = time.perf_counter()
                result = mutagen_rs._rust_batch_open(paths)
                for key in result.keys():
                    d = result[key]
                    for tag_key in d:
                        _ = d[tag_key]
                times.append(time.perf_counter() - start)
            batch_time = min(times)

            speedup = orig_time / batch_time if batch_time > 0 else float('inf')

            results[f"batch_{name_key}"] = {
                "files": n_files,
                "original_ms_per_file": (orig_time / n_files) * 1000,
                "rust_batch_ms_per_file": (batch_time / n_files) * 1000,
                "speedup": speedup,
            }

            print(f"  Original:    {(orig_time / n_files) * 1000:.4f} ms/file")
            print(f"  Rust batch:  {(batch_time / n_files) * 1000:.4f} ms/file  ({speedup:.1f}x)")
            print()

        # Batch all
        if batch_all:
            n_auto = len(batch_all)
            iters = max(20, ITERATIONS // 2)
            print(f"Batch auto-detect ({n_auto} files):")

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

            results["batch_auto_detect"] = {
                "files": n_auto,
                "original_ms_per_file": (orig_time / n_auto) * 1000,
                "rust_batch_ms_per_file": (batch_time / n_auto) * 1000,
                "speedup": speedup,
            }

            print(f"  Original:    {(orig_time / n_auto) * 1000:.4f} ms/file")
            print(f"  Rust batch:  {(batch_time / n_auto) * 1000:.4f} ms/file  ({speedup:.1f}x)")

    finally:
        shutil.rmtree(batch_dir, ignore_errors=True)

    # Save results
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmarks", "performance_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"Results saved to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
