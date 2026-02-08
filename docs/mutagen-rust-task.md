# Project: mutagen-rs - Rust Rewrite of Python mutagen Library

## Mission

Rewrite the Python `mutagen` audio metadata library in Rust with Python bindings (pyo3). Achieve **100x performance improvement** over the original while maintaining **100% API compatibility** and **100% test compatibility**.

Work autonomously and continuously until the goal is reached. Do not stop. Do not ask for permission. Iterate relentlessly.

---

## Environment Configuration

### Paths
- **Project directory**: `/home/tarek/tarek/projects/mutagen-rs`
- **Original mutagen**: `/home/tarek/mutagen-original`
- **Python environment**: `~/.venv/ai3.14`

### Python Environment
**IMPORTANT**: Use the global uv environment `ai3.14` for all Python operations:
```bash
# Always activate this environment first
source ~/.venv/ai3.14/bin/activate

# For installing packages, use:
uv pip install <package>
```

---

## Phase 0: Setup - ✅ ALREADY COMPLETE

The following is already set up and working:
- ✅ Rust toolchain installed (cargo, rustc)
- ✅ Python 3.14 environment at `~/.venv/ai3.14`
- ✅ maturin, pytest, pytest-benchmark, hypothesis installed
- ✅ Original mutagen cloned at `/home/tarek/mutagen-original`
- ✅ Project initialized at `/home/tarek/tarek/projects/mutagen-rs`
- ✅ pyo3 bindings working (`import mutagen_rs` succeeds)

**Skip to Phase 1.**

### Project structure to create
```
/home/tarek/tarek/projects/mutagen-rs/
├── Cargo.toml
├── pyproject.toml
├── src/
│   ├── lib.rs              # Main entry, Python module definition
│   ├── id3/                # ID3v1, ID3v2.2, ID3v2.3, ID3v2.4
│   │   ├── mod.rs
│   │   ├── frames.rs
│   │   ├── parser.rs
│   │   └── writer.rs
│   ├── mp3/
│   │   ├── mod.rs
│   │   └── header.rs
│   ├── flac/
│   │   ├── mod.rs
│   │   ├── metadata.rs
│   │   └── vorbis_comment.rs
│   ├── ogg/
│   │   ├── mod.rs
│   │   └── vorbis.rs
│   ├── mp4/
│   │   ├── mod.rs
│   │   └── atoms.rs
│   ├── apev2/
│   │   └── mod.rs
│   ├── asf/
│   │   └── mod.rs
│   └── common/
│       ├── mod.rs
│       ├── error.rs
│       └── tags.rs
├── tests/
│   ├── test_api_compat.py  # Must pass all original mutagen tests
│   └── test_performance.py # Benchmark comparisons
├── benches/
│   └── benchmarks.rs       # Rust-native benchmarks
└── test_files/             # Sample audio files for testing
```

---

## Phase 1: Gather Test Assets and Baseline

### Step 1.1: Collect test audio files
```bash
mkdir -p /home/tarek/tarek/projects/mutagen-rs/test_files

# Copy test files from original mutagen
cp -r /home/tarek/mutagen-original/tests/data/* /home/tarek/tarek/projects/mutagen-rs/test_files/

# Generate additional synthetic test files for benchmarking
python3 << 'EOF'
import os
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis

test_dir = "/home/tarek/tarek/projects/mutagen-rs/test_files/benchmark"
os.makedirs(test_dir, exist_ok=True)

# We'll use existing files and just document what we need
print("Test files ready in:", test_dir)
print("Use files from mutagen-original/tests/data for comprehensive testing")
EOF
```

### Step 1.2: Create baseline benchmark script
Create `/home/tarek/tarek/projects/mutagen-rs/baseline_benchmark.py`:
```python
#!/usr/bin/env python3
"""Baseline benchmarks for original mutagen library."""
import time
import statistics
import json
from pathlib import Path
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

TEST_DIR = Path("/home/tarek/tarek/projects/mutagen-rs/test_files")
RESULTS_FILE = Path("/home/tarek/tarek/projects/mutagen-rs/baseline_results.json")
ITERATIONS = 1000

def benchmark(func, iterations=ITERATIONS):
    """Run function multiple times and return stats."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        func()
        end = time.perf_counter_ns()
        times.append(end - start)
    return {
        "mean_ns": statistics.mean(times),
        "median_ns": statistics.median(times),
        "min_ns": min(times),
        "max_ns": max(times),
        "stdev_ns": statistics.stdev(times) if len(times) > 1 else 0,
        "iterations": iterations
    }

def find_test_file(patterns):
    """Find first matching test file."""
    for pattern in patterns:
        files = list(TEST_DIR.rglob(pattern))
        if files:
            return files[0]
    return None

def run_benchmarks():
    results = {}
    
    # MP3/ID3 benchmarks
    mp3_file = find_test_file(["*.mp3"])
    if mp3_file:
        print(f"Benchmarking MP3: {mp3_file}")
        results["mp3_open"] = benchmark(lambda: MP3(mp3_file))
        results["id3_open"] = benchmark(lambda: ID3(mp3_file))
        
        mp3 = MP3(mp3_file)
        results["mp3_read_all_tags"] = benchmark(lambda: dict(mp3.tags) if mp3.tags else {})
    
    # FLAC benchmarks
    flac_file = find_test_file(["*.flac"])
    if flac_file:
        print(f"Benchmarking FLAC: {flac_file}")
        results["flac_open"] = benchmark(lambda: FLAC(flac_file))
        flac = FLAC(flac_file)
        results["flac_read_tags"] = benchmark(lambda: dict(flac.tags) if flac.tags else {})
    
    # OGG benchmarks
    ogg_file = find_test_file(["*.ogg"])
    if ogg_file:
        print(f"Benchmarking OGG: {ogg_file}")
        results["ogg_open"] = benchmark(lambda: OggVorbis(ogg_file))
    
    # MP4 benchmarks
    mp4_file = find_test_file(["*.m4a", "*.mp4"])
    if mp4_file:
        print(f"Benchmarking MP4: {mp4_file}")
        results["mp4_open"] = benchmark(lambda: MP4(mp4_file))
    
    # Generic mutagen.File auto-detection
    if mp3_file:
        results["auto_detect_mp3"] = benchmark(lambda: mutagen.File(mp3_file))
    
    # Save results
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nBaseline results saved to {RESULTS_FILE}")
    print("\nSummary (mean times):")
    for name, stats in results.items():
        print(f"  {name}: {stats['mean_ns']/1000:.2f} µs")
    
    return results

if __name__ == "__main__":
    run_benchmarks()
```

### Step 1.3: Run baseline and record results
```bash
cd /home/tarek/tarek/projects/mutagen-rs
python3 baseline_benchmark.py
cat baseline_results.json
```

**IMPORTANT**: Record these baseline numbers. Your goal is 100x improvement on each metric.

---

## Phase 2: Implement Core Rust Library

### Priority order (implement in this sequence):
1. **ID3v2** - Most common, most complex, highest impact
2. **MP3** - Depends on ID3, very common format
3. **FLAC** - Simpler format, Vorbis comments
4. **OGG Vorbis** - Shares code with FLAC
5. **MP4/M4A** - Different atom structure
6. **APEv2** - Simpler tag format
7. **ID3v1** - Legacy, simple
8. **ASF/WMA** - Lower priority

### Implementation rules:

1. **Use zero-copy parsing wherever possible**
   - Use `&[u8]` slices instead of copying data
   - Use `memmap2` for file access
   - Use `bstr` for binary string handling

2. **Parse lazily**
   - Don't parse tags until accessed
   - Cache parsed results

3. **Match mutagen's API exactly**
   - Same class names
   - Same method names
   - Same exceptions/errors
   - Same return types

4. **Cargo.toml dependencies**:
```toml
[package]
name = "mutagen_rs"
version = "0.1.0"
edition = "2021"

[lib]
name = "mutagen_rs"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.20", features = ["extension-module"] }
memmap2 = "0.9"
thiserror = "1.0"
bitflags = "2.4"
encoding_rs = "0.8"
byteorder = "1.5"

[profile.release]
lto = true
codegen-units = 1
panic = "abort"
strip = true
```

### Example: Starting with ID3v2 parser

Create `/home/tarek/tarek/projects/mutagen-rs/src/id3/parser.rs`:
```rust
use std::io::{Read, Seek, SeekFrom};
use byteorder::{BigEndian, ReadBytesExt};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ID3Error {
    #[error("Invalid ID3 header")]
    InvalidHeader,
    #[error("Unsupported ID3 version: {0}.{1}")]
    UnsupportedVersion(u8, u8),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

pub struct ID3Header {
    pub version: (u8, u8),
    pub flags: u8,
    pub size: u32,
}

impl ID3Header {
    pub fn parse<R: Read>(reader: &mut R) -> Result<Option<Self>, ID3Error> {
        let mut magic = [0u8; 3];
        reader.read_exact(&mut magic)?;
        
        if &magic != b"ID3" {
            return Ok(None);
        }
        
        let major = reader.read_u8()?;
        let minor = reader.read_u8()?;
        let flags = reader.read_u8()?;
        
        // Syncsafe integer
        let mut size_bytes = [0u8; 4];
        reader.read_exact(&mut size_bytes)?;
        let size = ((size_bytes[0] as u32) << 21)
            | ((size_bytes[1] as u32) << 14)
            | ((size_bytes[2] as u32) << 7)
            | (size_bytes[3] as u32);
        
        Ok(Some(ID3Header {
            version: (major, minor),
            flags,
            size,
        }))
    }
}

// Continue implementing frames, etc.
```

---

## Phase 3: Python Bindings

### Create pyo3 module structure

`/home/tarek/tarek/projects/mutagen-rs/src/lib.rs`:
```rust
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

mod id3;
mod mp3;
mod flac;
mod common;

/// MP3 file handler - compatible with mutagen.mp3.MP3
#[pyclass]
struct MP3 {
    // Internal state
}

#[pymethods]
impl MP3 {
    #[new]
    fn new(filename: &str) -> PyResult<Self> {
        // Implementation
        todo!()
    }
    
    #[getter]
    fn tags(&self) -> PyResult<Option<PyObject>> {
        todo!()
    }
    
    #[getter]
    fn info(&self) -> PyResult<PyObject> {
        todo!()
    }
    
    fn save(&self) -> PyResult<()> {
        todo!()
    }
}

/// ID3 tag handler - compatible with mutagen.id3.ID3
#[pyclass]
struct ID3 {
    // Internal state
}

#[pymethods]
impl ID3 {
    #[new]
    fn new(filename: &str) -> PyResult<Self> {
        todo!()
    }
    
    fn __getitem__(&self, key: &str) -> PyResult<PyObject> {
        todo!()
    }
    
    fn __setitem__(&mut self, key: &str, value: PyObject) -> PyResult<()> {
        todo!()
    }
    
    fn __contains__(&self, key: &str) -> bool {
        todo!()
    }
    
    fn keys(&self) -> Vec<String> {
        todo!()
    }
    
    fn values(&self) -> Vec<PyObject> {
        todo!()
    }
    
    fn items(&self) -> Vec<(String, PyObject)> {
        todo!()
    }
}

/// Main module
#[pymodule]
fn mutagen_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<MP3>()?;
    m.add_class::<ID3>()?;
    // Add more classes as implemented
    Ok(())
}
```

---

## Phase 4: Testing Strategy

### 4.1 API Compatibility Tests

Create `/home/tarek/tarek/projects/mutagen-rs/tests/test_api_compat.py`:
```python
#!/usr/bin/env python3
"""
API compatibility tests.
Every test that passes with mutagen must pass with mutagen_rs.
"""
import pytest
import sys
from pathlib import Path

# Test both implementations
TEST_DIR = Path("/home/tarek/tarek/projects/mutagen-rs/test_files")

def get_implementations():
    """Return both mutagen and mutagen_rs for comparison testing."""
    import mutagen as original
    try:
        import mutagen_rs as rust
        return [("original", original), ("rust", rust)]
    except ImportError:
        return [("original", original)]

class TestMP3Compat:
    @pytest.fixture(params=get_implementations(), ids=lambda x: x[0])
    def impl(self, request):
        return request.param[1]
    
    def test_open_mp3(self, impl):
        mp3_files = list(TEST_DIR.rglob("*.mp3"))
        if not mp3_files:
            pytest.skip("No MP3 files found")
        
        for f in mp3_files[:10]:  # Test first 10
            audio = impl.mp3.MP3(str(f))
            assert audio is not None
    
    def test_read_tags(self, impl):
        mp3_files = list(TEST_DIR.rglob("*.mp3"))
        if not mp3_files:
            pytest.skip("No MP3 files found")
        
        audio = impl.mp3.MP3(str(mp3_files[0]))
        if audio.tags:
            # Should be able to iterate
            for key in audio.tags.keys():
                assert isinstance(key, str)

class TestID3Compat:
    def test_id3_tags_identical(self):
        """Verify rust implementation returns identical data."""
        import mutagen.id3 as original_id3
        try:
            import mutagen_rs
        except ImportError:
            pytest.skip("mutagen_rs not built yet")
        
        mp3_files = list(TEST_DIR.rglob("*.mp3"))
        if not mp3_files:
            pytest.skip("No MP3 files found")
        
        for f in mp3_files[:10]:
            orig = original_id3.ID3(str(f))
            rust = mutagen_rs.ID3(str(f))
            
            # Same keys
            assert set(orig.keys()) == set(rust.keys())
            
            # Same values
            for key in orig.keys():
                assert str(orig[key]) == str(rust[key])

# Run original mutagen test suite against our implementation
class TestOriginalTestSuite:
    """
    Import and run tests from the original mutagen test suite.
    """
    def test_run_original_id3_tests(self):
        """Run original ID3 tests with our implementation."""
        # This patches mutagen with mutagen_rs and runs original tests
        pass  # Implement based on original test structure

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 4.2 Performance Benchmark Tests

Create `/home/tarek/tarek/projects/mutagen-rs/tests/test_performance.py`:
```python
#!/usr/bin/env python3
"""
Performance benchmarks comparing mutagen vs mutagen_rs.
Goal: 100x improvement.
"""
import time
import json
import statistics
from pathlib import Path

BASELINE_FILE = Path("/home/tarek/tarek/projects/mutagen-rs/baseline_results.json")
ITERATIONS = 1000

def load_baseline():
    with open(BASELINE_FILE) as f:
        return json.load(f)

def benchmark(func, iterations=ITERATIONS):
    times = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        func()
        end = time.perf_counter_ns()
        times.append(end - start)
    return {
        "mean_ns": statistics.mean(times),
        "median_ns": statistics.median(times),
        "min_ns": min(times),
    }

def run_comparison():
    import mutagen
    import mutagen.mp3
    import mutagen.id3
    
    try:
        import mutagen_rs
    except ImportError:
        print("ERROR: mutagen_rs not built. Run: maturin develop --release")
        return
    
    baseline = load_baseline()
    TEST_DIR = Path("/home/tarek/tarek/projects/mutagen-rs/test_files")
    
    mp3_file = next(TEST_DIR.rglob("*.mp3"), None)
    if not mp3_file:
        print("No MP3 test files found")
        return
    
    results = {}
    
    # MP3 open benchmark
    print(f"\nBenchmarking with: {mp3_file}")
    
    rust_mp3 = benchmark(lambda: mutagen_rs.MP3(str(mp3_file)))
    orig_mp3 = baseline.get("mp3_open", {})
    
    if orig_mp3:
        speedup = orig_mp3["mean_ns"] / rust_mp3["mean_ns"]
        results["mp3_open"] = {
            "original_ns": orig_mp3["mean_ns"],
            "rust_ns": rust_mp3["mean_ns"],
            "speedup": speedup,
            "target_met": speedup >= 100
        }
        print(f"MP3 open: {speedup:.1f}x speedup {'✓' if speedup >= 100 else '✗'}")
    
    # ID3 benchmark
    rust_id3 = benchmark(lambda: mutagen_rs.ID3(str(mp3_file)))
    orig_id3 = baseline.get("id3_open", {})
    
    if orig_id3:
        speedup = orig_id3["mean_ns"] / rust_id3["mean_ns"]
        results["id3_open"] = {
            "original_ns": orig_id3["mean_ns"],
            "rust_ns": rust_id3["mean_ns"],
            "speedup": speedup,
            "target_met": speedup >= 100
        }
        print(f"ID3 open: {speedup:.1f}x speedup {'✓' if speedup >= 100 else '✗'}")
    
    # Summary
    print("\n" + "="*50)
    all_met = all(r.get("target_met", False) for r in results.values())
    if all_met:
        print("🎉 ALL TARGETS MET! 100x improvement achieved!")
    else:
        not_met = [k for k, v in results.items() if not v.get("target_met")]
        print(f"Targets not yet met: {not_met}")
        print("Keep optimizing!")
    
    # Save results
    with open("/home/tarek/tarek/projects/mutagen-rs/performance_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return results

if __name__ == "__main__":
    run_comparison()
```

---

## Phase 5: Optimization Loop

**Run this loop continuously until 100x is achieved:**

```bash
#!/bin/bash
# /home/tarek/tarek/projects/mutagen-rs/optimize_loop.sh

cd /home/tarek/tarek/projects/mutagen-rs

while true; do
    echo "=========================================="
    echo "Building release..."
    echo "=========================================="
    maturin develop --release
    
    if [ $? -ne 0 ]; then
        echo "Build failed. Fixing..."
        # Claude: analyze error and fix
        continue
    fi
    
    echo "=========================================="
    echo "Running compatibility tests..."
    echo "=========================================="
    python3 -m pytest tests/test_api_compat.py -v
    
    if [ $? -ne 0 ]; then
        echo "Tests failed. Fixing..."
        # Claude: analyze failures and fix
        continue
    fi
    
    echo "=========================================="
    echo "Running performance benchmarks..."
    echo "=========================================="
    python3 tests/test_performance.py
    
    # Check if 100x achieved
    if python3 -c "
import json
with open('performance_results.json') as f:
    results = json.load(f)
    all_met = all(r.get('target_met', False) for r in results.values())
    exit(0 if all_met else 1)
    "; then
        echo "🎉 SUCCESS! 100x improvement achieved!"
        break
    fi
    
    echo "Target not met. Continuing optimization..."
    # Claude: profile, identify bottlenecks, optimize
done
```

---

## Phase 6: Optimization Techniques to Apply

When performance is not yet 100x, apply these optimizations in order:

### Level 1: Low-hanging fruit
- [ ] Enable LTO in Cargo.toml
- [ ] Use `--release` builds
- [ ] Use `memmap2` instead of reading files into memory
- [ ] Use `&str` and `&[u8]` instead of `String` and `Vec<u8>`

### Level 2: Parsing optimizations
- [ ] Parse lazily - don't decode tags until accessed
- [ ] Cache decoded values
- [ ] Use SIMD for scanning (find ID3 header, sync bytes)
- [ ] Avoid UTF-8 validation when not needed

### Level 3: Advanced
- [ ] Use `unsafe` for hot paths (with careful review)
- [ ] Custom allocator for frame parsing
- [ ] Batch operations
- [ ] Prefetch file data

### Profiling commands:
```bash
# CPU profiling
cargo install flamegraph
cargo flamegraph --release -- <benchmark_binary>

# Micro-benchmarks
cargo bench

# Python-level profiling
python3 -m cProfile -s cumtime tests/test_performance.py
```

---

## Success Criteria

You are DONE when ALL of these are true:

1. **Performance**: All benchmarks show ≥100x speedup over original mutagen
2. **Compatibility**: 100% of original mutagen tests pass with mutagen_rs
3. **API Parity**: Drop-in replacement - same classes, methods, attributes
4. **Formats supported**: MP3/ID3, FLAC, OGG, MP4 at minimum
5. **Read AND Write**: Both reading and writing tags works correctly

---

## Progress Tracking

Create `/home/tarek/tarek/projects/mutagen-rs/PROGRESS.md` and update it after each session:

```markdown
# mutagen-rs Progress

## Current Status
- [ ] Phase 0: Setup complete
- [ ] Phase 1: Baseline recorded
- [ ] Phase 2: Core implementation
  - [ ] ID3v2 parser
  - [ ] MP3 handler
  - [ ] FLAC handler
  - [ ] OGG handler
  - [ ] MP4 handler
- [ ] Phase 3: Python bindings
- [ ] Phase 4: Tests passing
- [ ] Phase 5: 100x achieved

## Benchmark History
| Date | MP3 Open | ID3 Open | FLAC Open | Notes |
|------|----------|----------|-----------|-------|
| YYYY-MM-DD | Xx | Xx | Xx | Initial |

## Blockers
- None

## Next Actions
1. ...
```

---

## IMPORTANT RULES

1. **Never stop** - If something fails, fix it and continue
2. **Never ask for permission** - You have full sudo access, use it
3. **Commit often** - `git commit` after each working milestone
4. **Benchmark constantly** - Run benchmarks after every change
5. **Tests must pass** - Never sacrifice correctness for speed
6. **Document progress** - Update PROGRESS.md regularly
7. **Profile before optimizing** - Don't guess where slowness is

---

## Quick Start Commands

```bash
# Navigate to project (Phase 0 already complete)
cd /home/tarek/tarek/projects/mutagen-rs
source ~/.venv/ai3.14/bin/activate
source ~/.cargo/env

# Initialize git if not done
git init 2>/dev/null || true
git add -A && git commit -m "Initial setup" 2>/dev/null || true

# Development loop (run continuously)
maturin develop --release && python3 -m pytest tests/ -v && python3 tests/test_performance.py

# When stuck, profile:
cargo flamegraph --release
```

---

## BEGIN

Start now. Phase 0 is complete. Begin with Phase 1 - create test files directory and run baseline benchmarks. Do not stop until 100x is achieved.