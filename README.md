# mutagen-rs

[![CI](https://github.com/AiBrush/mutagen-rs/actions/workflows/CI.yml/badge.svg)](https://github.com/AiBrush/mutagen-rs/actions/workflows/CI.yml)
[![PyPI](https://img.shields.io/pypi/v/mutagen-rs)](https://pypi.org/project/mutagen-rs/)
[![Python](https://img.shields.io/pypi/pyversions/mutagen-rs)](https://pypi.org/project/mutagen-rs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

High-performance audio metadata library written in Rust with Python bindings. Drop-in replacement for Python's [mutagen](https://github.com/quodlibet/mutagen) with **up to 430x faster** metadata parsing.

## Performance

All benchmarks measure full tag parsing + info extraction + iteration of all keys/values.

### Single-file (sequential)

| Format | mutagen (Python) | mutagen-rs cold | mutagen-rs warm | Cold speedup | Warm speedup |
|--------|-----------------|-----------------|-----------------|-------------|-------------|
| MP3    | 0.286 ms/file   | 0.012 ms/file   | 0.0009 ms/file  | **24x**     | **337x**    |
| FLAC   | 0.123 ms/file   | 0.011 ms/file   | 0.0007 ms/file  | **11x**     | **167x**    |
| OGG    | 0.254 ms/file   | 0.020 ms/file   | 0.0006 ms/file  | **13x**     | **397x**    |
| MP4    | 0.253 ms/file   | 0.013 ms/file   | 0.0007 ms/file  | **20x**     | **382x**    |
| Auto   | 0.345 ms/file   | 0.014 ms/file   | 0.0008 ms/file  | **24x**     | **432x**    |

### Batch (Rust rayon parallel vs Python sequential)

| Format | mutagen (Python) | mutagen-rs batch | Speedup |
|--------|-----------------|------------------|---------|
| MP3    | 0.313 ms/file   | 0.009 ms/file    | **34x** |
| FLAC   | 0.122 ms/file   | 0.012 ms/file    | **10x** |
| OGG    | 0.241 ms/file   | 0.032 ms/file    | **8x**  |
| MP4    | 0.284 ms/file   | 0.014 ms/file    | **20x** |
| Auto   | 0.363 ms/file   | 0.020 ms/file    | **19x** |

**Methodology:**
- **Cold**: Both file and result caches cleared. Both sides read from disk (OS page cache benefits both equally).
- **Warm**: File data + parsed result cached in Rust. Returns shallow dict copy. Represents real-world repeated access (e.g., music library, playback queue).
- **Batch**: Rust uses rayon thread pool for multi-core parallelism. Cold cache with unique files.
- All benchmarks iterate all tag keys/values to force full materialization.

## Supported Formats

| Format     | Read | Write | Tags                    |
|------------|------|-------|-------------------------|
| MP3        | Yes  | Yes   | ID3v1, ID3v2.2/2.3/2.4 |
| FLAC       | Yes  | Yes   | Vorbis Comments         |
| OGG Vorbis | Yes  | Yes   | Vorbis Comments         |
| MP4/M4A    | Yes  | No    | iTunes-style ilst atoms |

## Installation

```bash
pip install mutagen-rs
```

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
- **Interned keys**: `pyo3::intern!` for repeated Python string creation
- **SIMD search**: `memchr`/`memmem` for MP3 sync finding and Vorbis key=value splitting

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

## License

MIT
