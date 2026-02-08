# Mission: Make mutagen-rs 10x Faster Than Lofty

## Your Goal

You are tasked with optimizing the `mutagen-rs` Rust library for audio metadata parsing until it is **10x faster than lofty-rs** across all formats (MP3, FLAC, OGG, MP4).

**Do not stop until you achieve this goal.**

---

## Phase 1: Setup & Baseline

1. **Clone lofty-rs** from GitHub as your reference and competitor:
   ```
   it's already in /home/tarek/tarek/projects/mutagen-rs/lofty-rs
   ```

2. **Set up the mutagen-bench project** (provided in this directory) or create your own benchmarking harness.

3. **Establish baseline measurements** for both libraries:
   - Single-file parse times per format
   - Batch processing throughput
   - Memory allocation counts
   - Document these numbers clearly

4. **Study lofty's implementation** deeply:
   - How do they parse each format?
   - What optimizations do they use?
   - Where are they potentially slow?
   - What can we do differently/better?

---

## Phase 2: Optimization Loop

Execute this loop continuously until 10x is achieved:

```
while (our_speed < lofty_speed * 10) {
    1. Profile current implementation
    2. Identify the biggest bottleneck
    3. Research optimization techniques
    4. Implement improvement
    5. Benchmark and verify
    6. Document what worked/didn't work
    7. Repeat
}
```

### Optimization Strategies to Explore

**Be creative. Try unconventional approaches. Think outside the box.**

#### Memory & Allocation
- [ ] Zero-copy parsing everywhere possible
- [ ] Arena allocators for temporary data
- [ ] Stack-allocated small buffers (`SmallVec`, `ArrayVec`)
- [ ] Eliminate all unnecessary `String` allocations
- [ ] Use `Cow<str>` and `Cow<[u8]>` aggressively
- [ ] Pre-allocate with exact capacities
- [ ] Consider bump allocators for parsing phases
- [ ] Memory-mapped file reading

#### SIMD & Vectorization
- [ ] Use `memchr` for all byte searches (already done, but verify optimal usage)
- [ ] SIMD for sync word scanning in MP3
- [ ] Vectorized UTF-8 validation
- [ ] SIMD for syncsafe integer decoding
- [ ] Consider `simd-json` patterns for parsing
- [ ] Explore `std::simd` (nightly) or `packed_simd`
- [ ] Hand-written assembly for hot paths (if justified by profiling)

#### Parsing Techniques
- [ ] Lazy parsing - only parse what's accessed
- [ ] Skip unnecessary data entirely (don't even read it)
- [ ] Branchless parsing where possible
- [ ] Lookup tables instead of conditionals
- [ ] Inline critical functions (`#[inline(always)]`)
- [ ] Profile-guided optimization (PGO)
- [ ] Link-time optimization (LTO) - fat or thin

#### Data Structures
- [ ] Cache-friendly memory layouts
- [ ] Consider `IndexMap` vs `HashMap`
- [ ] Perfect hashing for known key sets
- [ ] Interned strings for common tag names
- [ ] Flat structures instead of nested

#### I/O Optimization
- [ ] Read only necessary bytes (seek + partial read)
- [ ] Buffered reading with optimal buffer sizes
- [ ] `pread` for random access without seeking
- [ ] Consider `io_uring` for async batch I/O
- [ ] Memory mapping for large files

#### Compiler & Build
- [ ] `codegen-units = 1` for better optimization
- [ ] `lto = "fat"` for cross-crate inlining
- [ ] `panic = "abort"` to remove unwinding code
- [ ] Target-specific features: `-C target-cpu=native`
- [ ] Profile-guided optimization
- [ ] Try different allocators: `mimalloc`, `jemalloc`, `snmalloc`

#### Algorithmic Improvements
- [ ] Better format detection heuristics
- [ ] Faster sync word search algorithms
- [ ] Optimized VBR header parsing
- [ ] Streaming parsers that don't need full file in memory
- [ ] Parallel parsing of independent sections

---

## Phase 3: Advanced Techniques

If standard optimizations aren't enough, go deeper:

### Study the Competition
- Read lofty's source code line by line
- Understand their design decisions
- Find where they're not optimal
- Exploit their weaknesses

### Unconventional Approaches
- **Speculative parsing**: Assume common cases, verify later
- **Predictive branching**: Use likely/unlikely hints
- **Custom allocators**: Per-format optimized allocators
- **Unsafe optimizations**: Where safe code has overhead
- **Assembly intrinsics**: For the hottest hot paths
- **Compile-time computation**: Move work to build time

### Benchmark Methodology
- Use `criterion` for statistical rigor
- Test with real-world files (various sizes, tag counts)
- Test with synthetic worst-case files
- Profile with `perf`, `flamegraph`, `samply`
- Count allocations with `dhat` or custom allocator
- Measure cache misses with `cachegrind`

---

## Rules of Engagement

### DO:
- ✅ Work continuously until 10x is achieved
- ✅ Be creative and try unusual approaches
- ✅ Profile before optimizing (data-driven decisions)
- ✅ Document every experiment and result
- ✅ Learn from failures - they're information
- ✅ Read lofty's code for inspiration
- ✅ Use unsafe Rust where justified and safe
- ✅ Benchmark after every change
- ✅ Keep a log of what you tried and results
- ✅ Think about what makes this problem unique

### DON'T:
- ❌ Stop until you reach 10x
- ❌ Make changes without measuring impact
- ❌ Assume something won't work without trying
- ❌ Optimize blindly without profiling
- ❌ Give up when stuck - try a different approach
- ❌ Sacrifice correctness for speed (tests must pass)

---

## Success Criteria

You have succeeded when:

```
benchmark_result.our_time * 10 <= benchmark_result.lofty_time
```

For ALL formats:
- [ ] MP3 (ID3v2 parsing): 10x faster than lofty
- [ ] FLAC (StreamInfo + VorbisComment): 10x faster than lofty
- [ ] OGG Vorbis (headers + comments): 10x faster than lofty  
- [ ] MP4/M4A (atom tree + iTunes tags): 10x faster than lofty

---

## Progress Tracking

Maintain a file called `OPTIMIZATION_LOG.md` with:

```markdown
# Optimization Log

## Current Status
- MP3: X.Xx faster than lofty
- FLAC: X.Xx faster than lofty
- OGG: X.Xx faster than lofty
- MP4: X.Xx faster than lofty

## Experiments

### Experiment N: [Name]
- **Hypothesis**: ...
- **Change**: ...
- **Result**: +X% / -X% / no change
- **Keep/Revert**: ...
- **Learnings**: ...
```

---

## Mindset

This is a challenge. Lofty is a mature, well-optimized library. Beating it by 10x requires:

1. **Deep understanding** of the problem domain
2. **Creative thinking** about alternative approaches  
3. **Relentless iteration** and experimentation
4. **Rigorous measurement** to guide decisions
5. **Persistence** when progress is slow

You have unlimited time and compute. Use it.

**The goal is achievable. Keep working until you get there.**

---

## Getting Started

Begin now:

1. Set up the benchmark environment
2. Run initial benchmarks against lofty
3. Profile to find the first bottleneck
4. Start the optimization loop

Do not ask for permission. Do not wait for guidance. 

**Start optimizing. Don't stop until you hit 10x.**