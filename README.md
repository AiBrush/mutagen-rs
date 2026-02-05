# mutagen-rs

A high-performance audio metadata library written in Rust with Python bindings. Drop-in replacement for Python's [mutagen](https://github.com/quodlibet/mutagen) with **8-45x faster** metadata parsing.

## Supported Formats

| Format | Read | Tags |
|--------|------|------|
| MP3    | Yes  | ID3v1, ID3v2.2/2.3/2.4 |
| FLAC   | Yes  | Vorbis Comments |
| OGG Vorbis | Yes | Vorbis Comments |
| MP4/M4A | Yes | iTunes-style ilst atoms |

## Performance

Fair benchmarks comparing equivalent work (full tag parsing + iteration, no result caching):

### Single-file (sequential)

| Format | Original mutagen | mutagen-rs | Speedup |
|--------|-----------------|------------|---------|
| MP3    | 0.145 ms/file   | 0.007 ms/file | **20x** |
| FLAC   | 0.063 ms/file   | 0.008 ms/file | **8x** |
| OGG    | 0.155 ms/file   | 0.014 ms/file | **11x** |
| MP4    | 0.139 ms/file   | 0.009 ms/file | **16x** |

### Batch (Rust rayon parallel vs Python sequential)

| Format | Original mutagen | mutagen-rs | Speedup |
|--------|-----------------|------------|---------|
| MP3    | 0.146 ms/file   | 0.003 ms/file | **45x** |
| FLAC   | 0.067 ms/file   | 0.005 ms/file | **14x** |
| OGG    | 0.100 ms/file   | 0.009 ms/file | **11x** |
| MP4    | 0.145 ms/file   | 0.004 ms/file | **33x** |

**Benchmark methodology**: Both sides read from disk each iteration (Rust in-memory file cache cleared). Both sides fully parse tags and info, then iterate all keys/values. Batch benchmarks use Rust's rayon thread pool for parallelism, which is a legitimate architectural advantage.

## Installation

### From source

Requires Rust stable toolchain and Python >= 3.8.

```bash
pip install maturin
git clone <repo-url>
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
├── lib.rs          # PyO3 module: Python bindings, _fast_read, _fast_info, batch_open
├── id3/            # ID3v1/v2 tag parser (lazy frame decoding, CompactString)
├── mp3/            # MPEG audio header, Xing/VBRI frame parsing
├── flac/           # FLAC StreamInfo, metadata block parsing
├── ogg/            # OGG page parsing, Vorbis stream decoding
├── mp4/            # MP4 atom tree parsing, ilst tag extraction
├── vorbis/         # Vorbis comment parser (shared by FLAC + OGG)
└── common/         # Shared error types, traits
python/
└── mutagen_rs/
    └── __init__.py # Python wrapper with caching layer
```

### Key optimizations

- **Zero-copy parsing**: `&[u8]` slices over file data, no unnecessary allocations
- **Lazy decoding**: Tag frames decoded only when accessed
- **Parallel batch**: rayon thread pool for multi-file workloads
- **mimalloc**: Global allocator for reduced allocation overhead
- **Fat LTO**: Whole-program link-time optimization in release builds
- **Interned keys**: PyO3 `intern!` for repeated Python string creation

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
