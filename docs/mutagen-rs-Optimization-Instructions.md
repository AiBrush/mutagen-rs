# mutagen-rs Optimization Instructions

## Overview

This document contains instructions for optimizing mutagen-rs in two phases:
1. **Phase 1**: Low-level Rust optimizations (pure parsing performance)
2. **Phase 2**: Python/PyO3 integration optimizations (FFI overhead reduction)

Current performance: ~7-20x faster than Python mutagen
Target performance: 50x+ faster than Python mutagen

---

# Phase 1: Low-Level Rust Optimizations

## 1.1 Memory-Mapped I/O

**Goal**: Eliminate file read copies for large files

**Instructions**:
1. Add `memmap2` crate to Cargo.toml dependencies
2. Create a new function variant for each file parser that accepts memory-mapped data
3. For `MP3File::open()`, `FLACFile::open()`, `OggVorbisFile::open()`, `MP4File::open()`:
   - Open the file handle
   - Create a memory map using `unsafe { Mmap::map(&file) }`
   - Pass the mmap slice to the existing `parse(&[u8])` function
4. For batch operations, keep files memory-mapped until processing completes
5. Add a feature flag `mmap` to optionally enable this behavior
6. Benchmark both approaches and document the threshold file size where mmap becomes beneficial

---

## 1.2 Arena Allocator for Tag Parsing

**Goal**: Reduce allocation overhead when parsing many small strings

**Instructions**:
1. Add `bumpalo` crate to Cargo.toml dependencies
2. Create an `ArenaParser` struct that holds a `bumpalo::Bump` allocator
3. Modify the internal parsing functions to accept an optional arena reference
4. For VorbisComment parsing:
   - Allocate all comment strings from the arena instead of creating individual `String` objects
   - Store string slices (`&'arena str`) instead of owned strings where possible
5. For ID3 frame parsing:
   - Use the arena for frame text content
   - Use the arena for temporary buffers during encoding conversion
6. Create a `parse_with_arena()` variant for batch processing that reuses a single arena
7. Reset the arena between files in batch mode instead of deallocating

---

## 1.3 Unsafe Bounds Checking Elimination

**Goal**: Remove redundant bounds checks in validated hot paths

**Instructions**:
1. Identify hot loops in the codebase using profiling or code inspection:
   - MP3 sync scanning loop
   - ID3 frame iteration loop
   - VorbisComment parsing loop
   - MP4 atom traversal loop
   - OGG page scanning loop
2. For each hot loop:
   - First validate that the data slice has sufficient length at the loop entry
   - Replace `data[i]` with `unsafe { *data.get_unchecked(i) }` inside the validated region
   - Add clear safety comments explaining why the unchecked access is valid
3. Create helper macros or inline functions for common patterns:
   - `read_u32_be_unchecked(data, offset)`
   - `read_u32_le_unchecked(data, offset)`
   - `read_u16_be_unchecked(data, offset)`
4. Keep safe bounds-checked versions available for debug builds using `#[cfg(debug_assertions)]`

---

## 1.4 Target CPU Optimization

**Goal**: Enable CPU-specific optimizations

**Instructions**:
1. Update Cargo.toml to add CPU-specific build profiles:
   ```toml
   [profile.release]
   lto = true
   codegen-units = 1
   opt-level = 3
   
   [profile.release-native]
   inherits = "release"
   rustflags = ["-C", "target-cpu=native"]
   ```
2. Document in README how to build with native CPU optimizations
3. For distributed builds, create feature flags for common CPU feature sets:
   - `avx2` for modern Intel/AMD
   - `neon` for ARM64
4. Add runtime CPU feature detection for critical SIMD paths if needed

---

## 1.5 Profile-Guided Optimization Setup

**Goal**: Enable PGO for production builds

**Instructions**:
1. Create a `pgo/` directory in the project root
2. Create a script `pgo/collect-profile.sh` that:
   - Builds the library with profiling instrumentation enabled
   - Runs a representative workload (parsing many files of each format)
   - Merges the profile data
3. Create a script `pgo/build-optimized.sh` that:
   - Uses the collected profile data to build an optimized release
4. Document the PGO process in README
5. Consider adding a CI workflow that generates PGO-optimized releases

---

## 1.6 Branchless Code Patterns

**Goal**: Reduce branch mispredictions in hot paths

**Instructions**:
1. Identify branchy code in performance-critical sections:
   - Channel count determination from mode bits
   - Encoding type selection
   - Format detection score calculation
2. Convert simple if-else patterns to branchless arithmetic:
   - Use conditional moves: `let x = if cond { a } else { b }` → `let x = b + (a - b) * (cond as T)`
   - Use lookup tables for small fixed mappings
3. For format detection, use a scoring table instead of sequential if-else
4. Replace match statements on small enums with array lookups where appropriate
5. Benchmark each change to verify improvement (some branchless code can be slower)

---

## 1.7 Custom SIMD for MP3 Sync Scanning

**Goal**: Accelerate MP3 frame sync detection beyond memchr

**Instructions**:
1. Analyze the MP3 sync pattern requirements:
   - First byte must be 0xFF
   - Second byte must have upper 3 bits set (0xE0 mask)
   - Additional validation bits in bytes 2-3
2. Create a SIMD implementation under `#[cfg(target_arch = "x86_64")]`:
   - Use AVX2 intrinsics to scan 32 bytes at a time
   - Find 0xFF candidates with `_mm256_cmpeq_epi8`
   - Validate second byte pattern for each candidate
3. Create equivalent implementation for ARM NEON under `#[cfg(target_arch = "aarch64")]`
4. Provide a scalar fallback for other architectures
5. Use runtime feature detection with `std::arch::is_x86_feature_detected!`
6. Only use custom SIMD if benchmarks show improvement over memchr

---

## 1.8 Lazy Parsing Architecture

**Goal**: Parse only what's needed, when it's needed

**Instructions**:
1. Create `LazyTags` struct that stores:
   - Reference to the original data slice
   - Byte offsets and lengths for each tag frame (not parsed content)
2. Implement lazy parsing:
   - Initial parse only extracts frame boundaries (offset, length, frame ID)
   - Full frame content is parsed on first access
   - Cache parsed results after first access
3. For common access patterns (title, artist, album), provide fast-path methods
4. Implement `Iterator` that yields parsed frames on demand
5. This is particularly valuable for MP4 where atom tree traversal is expensive

---

## 1.9 String Interning

**Goal**: Deduplicate common strings across parsed files

**Instructions**:
1. Add `string-interner` or `lasso` crate to dependencies
2. Create a global or thread-local string interner for:
   - Frame IDs ("TIT2", "TPE1", "TALB", etc.)
   - Common tag keys ("TITLE", "ARTIST", "ALBUM", etc.)
   - MIME types ("image/jpeg", "image/png", etc.)
3. Return interned string handles instead of owned strings for known keys
4. Use `&'static str` for compile-time known strings
5. This reduces both allocation count and memory usage

---

## 1.10 Reduce UTF-8 Validation

**Goal**: Skip redundant UTF-8 validation

**Instructions**:
1. For Latin1 decoding, output is always valid - mark as such
2. For UTF-16 to UTF-8 transcoding, encoding_rs output is already valid
3. Use `String::from_utf8_unchecked` where input validity is guaranteed
4. For VorbisComment, most values are already valid UTF-8 - try zero-copy first:
   - Attempt `std::str::from_utf8()` 
   - Only allocate and use lossy conversion on failure
5. Add safety comments documenting why unchecked conversion is valid

---

# Phase 2: Python/PyO3 Integration Optimizations

## 2.1 Return JSON Instead of PyObjects

**Goal**: Minimize Python object creation in Rust

**Instructions**:
1. Add `serde` and `serde_json` crates to dependencies
2. Create `#[derive(Serialize)]` structs mirroring the tag structures
3. Implement `batch_open_json(filenames: Vec<String>) -> PyResult<Py<PyBytes>>`:
   - Parse all files in parallel (existing logic)
   - Serialize results to JSON
   - Return as Python bytes object
4. Let Python deserialize with `json.loads()` or `orjson.loads()`
5. Benchmark against current PyObject creation approach
6. Consider MessagePack (`rmp-serde`) as faster alternative to JSON

---

## 2.2 Interned Python Strings

**Goal**: Reuse Python string objects for common keys

**Instructions**:
1. Use `pyo3::intern!` macro for all repeated string keys:
   - Dictionary keys: "title", "artist", "album", "length", etc.
   - Frame IDs: "TIT2", "TPE1", "TALB", etc.
   - Format names: "mp3", "flac", "ogg", "mp4"
2. Create a module-level cache of interned strings initialized on module load
3. Replace all `PyDict::set_item("key", ...)` with `PyDict::set_item(intern!(py, "key"), ...)`
4. For dynamic keys (like TXXX descriptions), still use regular strings

---

## 2.3 Lazy Python Object Creation

**Goal**: Create Python objects only when accessed

**Instructions**:
1. Redesign `PyBatchResult` to store Rust data internally
2. Implement `__getitem__` to convert to Python object on first access
3. Cache converted objects after first access
4. For dictionary-style access patterns:
   - Store parsed data in Rust structs
   - Convert individual fields to Python only when `result["key"]` is called
5. Implement `__iter__` that yields lazily converted items
6. Add `to_dict()` method for users who need everything at once

---

## 2.4 Pre-allocated Python Containers

**Goal**: Reduce Python allocation overhead

**Instructions**:
1. For lists with known size:
   - Use `PyList::new(py, &items)` instead of building incrementally
   - Pre-calculate list size before creating
2. For dicts with known keys:
   - Calculate key count before creating dict
   - Consider using `PyDict::from_sequence` for bulk creation
3. For repeated operations:
   - Reuse Python list/dict objects where possible
   - Clear and refill instead of recreating

---

## 2.5 Reduce GIL Operations

**Goal**: Minimize GIL acquisition/release cycles

**Instructions**:
1. Audit all `Python::with_gil()` calls and consolidate
2. In batch operations:
   - Release GIL for entire parsing phase: `py.allow_threads(|| { ... })`
   - Acquire GIL once for all result conversions
3. Avoid acquiring GIL inside loops - restructure to batch operations
4. Document GIL behavior for users writing multi-threaded code
5. Consider `pyo3-asyncio` for async Python integration

---

## 2.6 Zero-Copy Python Bytes

**Goal**: Avoid copying binary data to Python

**Instructions**:
1. For album art and binary frames:
   - Store data in Rust `Arc<[u8]>` 
   - Return Python `memoryview` pointing to Rust memory
   - Ensure Rust data outlives Python reference
2. Implement Python buffer protocol for binary data access
3. Use `PyBytes::new_with()` to write directly into Python-managed memory
4. For read-only access, share Rust memory instead of copying

---

## 2.7 Streaming Results

**Goal**: Return results as they're parsed, not all at once

**Instructions**:
1. Create Python iterator class `BatchIterator`:
   - Holds receiver end of a channel
   - `__next__` blocks until next result available
2. Spawn parsing in background thread:
   - Parse files in parallel
   - Send results through channel as completed
3. Python can process results while parsing continues
4. Reduces peak memory usage for large batches
5. Provides faster time-to-first-result

---

## 2.8 Optimize Common Access Patterns

**Goal**: Fast paths for typical usage

**Instructions**:
1. Analyze common usage patterns:
   - `file["TIT2"]` - single tag access
   - `file.tags` - all tags as dict
   - `file.info.length` - single property
2. For single-tag access:
   - Return Python string directly without intermediate dict
   - Cache converted value
3. For `info` properties:
   - Store as Rust struct, convert individual fields on access
   - Use `#[pyo3(get)]` for simple numeric fields (zero-cost)
4. Add specialized methods: `get_title()`, `get_artist()`, etc.

---

## 2.9 Batch-Optimized Data Format

**Goal**: Minimize per-file overhead in batch mode

**Instructions**:
1. Design flat data structure for batch results:
   ```
   {
     "files": ["path1", "path2", ...],
     "lengths": [120.5, 180.3, ...],
     "titles": ["Song1", "Song2", ...],
     ...
   }
   ```
2. Column-oriented format reduces Python object count
3. Implement `to_dataframe()` for pandas integration
4. Single NumPy array for numeric fields (length, bitrate, sample_rate)
5. This trades random access for iteration efficiency

---

## 2.10 C Extension Alternative

**Goal**: Evaluate if raw C extension outperforms PyO3

**Instructions**:
1. Create minimal C wrapper using Python C API directly
2. Implement single-file and batch-file entry points
3. Benchmark against PyO3 implementation
4. If significantly faster, consider hybrid approach:
   - C extension for Python interface
   - Rust library for parsing logic
   - Link via C ABI
5. Document findings regardless of outcome

---

# Testing & Validation

## Benchmark Requirements

After implementing optimizations, validate with:

1. **Single-file benchmarks** for each format (MP3, FLAC, OGG, MP4)
2. **Batch benchmarks** with 100, 1000, 10000 files
3. **Memory usage** profiling with `memory_profiler`
4. **Comparison against Python mutagen** for same file set
5. **Comparison against lofty-rs** for pure Rust performance

## Success Criteria

- Single-file: ≥50x faster than Python mutagen
- Batch processing: ≥100x faster than Python mutagen
- Memory usage: ≤2x Python mutagen for same workload
- API compatibility: All existing tests pass

---

# Implementation Order

Recommended order based on effort vs. impact:

## Quick Wins (Do First)
1. 2.2 Interned Python Strings
2. 1.4 Target CPU Optimization
3. 2.5 Reduce GIL Operations
4. 1.3 Unsafe Bounds Checking (careful review required)

## Medium Effort, High Impact
5. 2.1 Return JSON Instead of PyObjects
6. 1.1 Memory-Mapped I/O
7. 2.3 Lazy Python Object Creation
8. 1.2 Arena Allocator

## Larger Refactors
9. 1.8 Lazy Parsing Architecture
10. 2.7 Streaming Results
11. 2.9 Batch-Optimized Data Format

## Advanced (If Still Needed)
12. 1.5 PGO Setup
13. 1.7 Custom SIMD
14. 2.10 C Extension Alternative

---

# Notes

- Always benchmark before and after each optimization
- Keep the unoptimized code path available for debugging
- Document all unsafe code with safety invariants
- Run full test suite after each change
- Profile to identify actual bottlenecks, don't guess