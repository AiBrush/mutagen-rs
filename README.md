# mutagen-rs

[![CI](https://github.com/AiBrush/mutagen-rs/actions/workflows/CI.yml/badge.svg)](https://github.com/AiBrush/mutagen-rs/actions/workflows/CI.yml)
[![PyPI](https://img.shields.io/pypi/v/mutagen-rs?color=blue)](https://pypi.org/project/mutagen-rs/)
[![crates.io](https://img.shields.io/crates/v/mutagen-rs?color=orange)](https://crates.io/crates/mutagen-rs)
[![docs.rs](https://docs.rs/mutagen-rs/badge.svg)](https://docs.rs/mutagen-rs)
[![Python](https://img.shields.io/pypi/pyversions/mutagen-rs)](https://pypi.org/project/mutagen-rs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/AiBrush/mutagen-rs)](https://github.com/AiBrush/mutagen-rs/releases)

High-performance audio metadata library written in Rust with Python bindings. Drop-in replacement for Python's [mutagen](https://github.com/quodlibet/mutagen) with **7-30x faster cold reads** and **100x+ faster** cached/batch processing on all formats.

## Performance

All benchmarks measure full tag parsing + info extraction + iteration of all keys/values.

### Single-file cold read (primary metric)

Cold = both file and result caches cleared. Both sides read from OS page cache.

| Format | mutagen (Python) | mutagen-rs cold | Speedup |
|--------|-----------------|-----------------|---------|
| MP3    | 0.289 ms/file   | 0.010 ms/file   | **29x** |
| FLAC   | 0.116 ms/file   | 0.009 ms/file   | **13x** |
| OGG    | 0.254 ms/file   | 0.015 ms/file   | **17x** |
| MP4    | 0.253 ms/file   | 0.011 ms/file   | **24x** |
| Auto   | 0.340 ms/file   | 0.011 ms/file   | **31x** |

### Single-file with result caching (warm)

Warm = file data + parsed result cached in Rust; returns a shallow dict copy. Represents real-world repeated access (e.g., music library UI, playback queue).

| Format | mutagen (Python) | mutagen-rs warm | Speedup |
|--------|-----------------|-----------------|---------|
| MP3    | 0.289 ms/file   | 0.0008 ms/file  | **343x** |
| FLAC   | 0.116 ms/file   | 0.0007 ms/file  | **159x** |
| OGG    | 0.254 ms/file   | 0.0006 ms/file  | **407x** |
| MP4    | 0.253 ms/file   | 0.0007 ms/file  | **385x** |

### Batch (rayon parallel vs Python sequential)

Batch uses Rust rayon parallelism with stat-based dedup vs Python sequential. 40 copies per file to simulate real music libraries with duplicates. Cold cache.

| Format | Files | mutagen (Python) | mutagen-rs batch | Speedup |
|--------|-------|-----------------|------------------|---------|
| MP3    | 760   | 0.294 ms/file   | 0.0011 ms/file   | **264x** |
| FLAC   | 280   | 0.124 ms/file   | 0.0010 ms/file   | **120x** |
| OGG    | 120   | 0.240 ms/file   | 0.0014 ms/file   | **169x** |
| MP4    | 360   | 0.268 ms/file   | 0.0012 ms/file   | **227x** |
| Auto   | 1520  | 0.333 ms/file   | 0.0013 ms/file   | **264x** |

### vs lofty-rs (Rust-to-Rust, in-memory, criterion)

Both parsing from `&[u8]` in memory. Uses [criterion](https://github.com/bheisler/criterion.rs) microbenchmarks. **Note**: mutagen-rs uses lazy parsing (defers frame decoding to access time), so these numbers reflect initial parse cost only, not full materialization.

| Format | mutagen-rs | lofty-rs | Speedup |
|--------|-----------|----------|---------|
| MP3 (large)  | 165 ns  | 42.0 us  | **254x** |
| FLAC (large) | 175 ns  | 57.1 us  | **326x** |
| OGG (large)  | 26 ns   | 457.5 us | **17,600x** |
| MP4 (large)  | 108 ns  | 64.1 us  | **594x** |
| MP3 (small)  | 165 ns  | 7.7 us   | **47x** |
| FLAC (small) | 227 ns  | 4.7 us   | **21x** |
| OGG (small)  | 26 ns   | 1.3 us   | **52x** |
| MP4 (small)  | 95 ns   | 4.4 us   | **46x** |

**Methodology notes:**
- Cold/warm benchmarks run on our development hardware. Results may differ on other systems (independent testing has measured 7-15x cold speedup).
- Batch speedup includes benefits from rayon parallelism (multi-core), not just faster parsing.
- The lofty-rs comparison is lazy-parse vs full-parse, so the speedup partly reflects deferred work rather than eliminated work.

## Supported Formats

| Format     | Read | Write | Tags                    |
|------------|------|-------|-------------------------|
| MP3        | Yes  | Yes   | ID3v1, ID3v2.2/2.3/2.4 |
| FLAC       | Yes  | Yes   | Vorbis Comments         |
| OGG Vorbis | Yes  | Yes   | Vorbis Comments         |
| MP4/M4A    | Yes  | No    | iTunes-style ilst atoms |

## Installation

### Python

```bash
pip install mutagen-rs
```

Pre-built wheels are available for Linux, macOS, and Windows across Python 3.9 - 3.13. See [PyPI](https://pypi.org/project/mutagen-rs/) for all available distributions.

### Rust

```bash
cargo add mutagen-rs
```

The Rust crate provides the core parsing library without Python bindings. Enable the `python` feature for PyO3 bindings. See [crates.io](https://crates.io/crates/mutagen-rs) and [docs.rs](https://docs.rs/mutagen-rs) for API documentation.

### From source

Requires Rust stable toolchain and Python >= 3.8.

```bash
pip install maturin
git clone https://github.com/AiBrush/mutagen-rs.git
cd mutagen-rs
maturin develop --release
```

## Usage

### Drop-in replacement API

```python
import mutagen_rs

# Same API as mutagen
f = mutagen_rs.MP3("song.mp3")
print(f.info.length)       # duration in seconds
print(f.info.sample_rate)  # e.g. 44100
print(f.info.channels)     # e.g. 2

# Access tags
for key in f.tags.keys():
    print(key, f[key])

# Auto-detect format
f = mutagen_rs.File("audio.flac")

# Other formats
f = mutagen_rs.FLAC("audio.flac")
f = mutagen_rs.OggVorbis("audio.ogg")
f = mutagen_rs.MP4("audio.m4a")
```

### Fast read API

For maximum throughput when you just need metadata as a Python dict:

```python
import mutagen_rs

# Returns a flat dict with info fields + all tags
d = mutagen_rs._fast_read("song.mp3")
print(d["length"], d["sample_rate"])

# Info-only (no tag parsing, fastest possible)
d = mutagen_rs._fast_info("song.mp3")
print(d["length"])
```

### Batch API

Process many files in parallel using Rust's rayon thread pool:

```python
import mutagen_rs

paths = ["song1.mp3", "song2.flac", "song3.ogg"]
result = mutagen_rs.batch_open(paths)

for path in result.keys():
    data = result[path]  # dict with info + tags
    print(path, data["length"])
```

## Architecture

```
src/
  lib.rs          # PyO3 module: Python bindings, _fast_read, batch_open
  id3/            # ID3v1/v2 tag parser (lazy frame decoding)
  mp3/            # MPEG audio header, Xing/VBRI parsing (SIMD sync finder)
  flac/           # FLAC StreamInfo, metadata block parsing
  ogg/            # OGG page parsing, Vorbis stream decoding
  mp4/            # MP4 atom tree parsing, ilst tag extraction
  vorbis/         # Vorbis comment parser (shared by FLAC + OGG)
  common/         # Shared error types, file I/O utilities
python/
  mutagen_rs/
    __init__.py   # Python wrapper with caching layer
```

### Key optimizations

- **Zero-copy parsing**: `&[u8]` slices over memory-mapped or cached file data
- **Lazy frame decoding**: ID3 frames decoded only when accessed
- **Two-level caching**: File data cache (eliminates I/O) + parsed result cache (returns `PyDict_Copy` in ~300ns)
- **Parallel batch processing**: rayon thread pool for multi-file workloads
- **Raw CPython FFI**: Direct `PyDict_SetItem`/`PyUnicode_FromStringAndSize` calls bypass PyO3 wrapper overhead
- **mimalloc**: Global allocator for reduced allocation overhead
- **Fat LTO**: Whole-program link-time optimization with `codegen-units = 1`
- **Interned keys**: `pyo3::intern!` for info fields + thread-local cache for tag keys (ID3 frame IDs, Vorbis comment keys)
- **SIMD search**: `memchr`/`memmem` for MP3 sync finding, Vorbis key=value splitting, and OGG page scanning
- **O(1) batch lookup**: HashMap index for batch result access (avoids O(n) linear search)

## Development

```bash
# Build
maturin develop --release

# Run tests
python -m pytest tests/ -v

# Run benchmarks
python tests/test_performance.py

# Full cycle
maturin develop --release && python -m pytest tests/ -v && python tests/test_performance.py
```

## Links

- [PyPI](https://pypi.org/project/mutagen-rs/) - Python package
- [crates.io](https://crates.io/crates/mutagen-rs) - Rust crate
- [docs.rs](https://docs.rs/mutagen-rs) - Rust API documentation
- [GitHub](https://github.com/AiBrush/mutagen-rs) - Source code and issues

## License

[MIT](LICENSE)
