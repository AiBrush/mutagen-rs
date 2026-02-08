"""Baseline benchmark for original mutagen library."""
import json
import time
import os
import mutagen
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

TEST_DIR = os.path.join(os.path.dirname(__file__), "test_files")

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

def benchmark_format(name, cls, paths, iterations=100):
    """Benchmark opening and reading tags for a format."""
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
                # Access common properties to force parsing
                if hasattr(f, 'info') and f.info:
                    _ = f.info.length
                    if hasattr(f.info, 'bitrate'):
                        _ = f.info.bitrate
                    if hasattr(f.info, 'sample_rate'):
                        _ = f.info.sample_rate
                if f.tags:
                    _ = list(f.tags.keys())
                    for k in f.tags.keys():
                        _ = f.tags[k]
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg = sum(times) / len(times)
    best = min(times)
    return {
        "format": name,
        "files": len(paths),
        "iterations": iterations,
        "avg_time_s": avg,
        "best_time_s": best,
        "avg_per_file_ms": (avg / len(paths)) * 1000,
        "best_per_file_ms": (best / len(paths)) * 1000,
    }

def benchmark_auto_detect(paths, iterations=100):
    """Benchmark mutagen.File() auto-detection."""
    all_paths = []
    for ps in paths.values():
        all_paths.extend(ps)

    if not all_paths:
        return None

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for p in all_paths:
            try:
                mutagen.File(p)
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg = sum(times) / len(times)
    best = min(times)
    return {
        "format": "auto_detect",
        "files": len(all_paths),
        "iterations": iterations,
        "avg_time_s": avg,
        "best_time_s": best,
        "avg_per_file_ms": (avg / len(all_paths)) * 1000,
        "best_per_file_ms": (best / len(all_paths)) * 1000,
    }

def main():
    files = find_test_files()
    print(f"Found test files: { {k: len(v) for k, v in files.items()} }")

    format_map = {
        "mp3": MP3,
        "flac": FLAC,
        "ogg": OggVorbis,
        "mp4": MP4,
    }

    results = {}
    for name, cls in format_map.items():
        paths = files.get(name, [])
        if paths:
            print(f"Benchmarking {name} ({len(paths)} files)...")
            result = benchmark_format(name, cls, paths)
            if result:
                results[name] = result
                print(f"  avg: {result['avg_per_file_ms']:.3f} ms/file, best: {result['best_per_file_ms']:.3f} ms/file")

    print("Benchmarking auto-detect...")
    auto_result = benchmark_auto_detect(files)
    if auto_result:
        results["auto_detect"] = auto_result
        print(f"  avg: {auto_result['avg_per_file_ms']:.3f} ms/file, best: {auto_result['best_per_file_ms']:.3f} ms/file")

    output_path = os.path.join(os.path.dirname(__file__), "baseline_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

if __name__ == "__main__":
    main()
