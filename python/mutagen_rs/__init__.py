"""mutagen_rs - Fast audio metadata library with Python caching layer."""

from .mutagen_rs import (
    # File handler types (wrapped by factory functions below)
    MP3 as _RustMP3,
    FLAC as _RustFLAC,
    OggVorbis as _RustOggVorbis,
    MP4 as _RustMP4,
    file_open as _rust_file_open,

    # Info types (re-exported as-is)
    MPEGInfo,
    StreamInfo,
    OggVorbisInfo,
    MP4Info,

    # Tag types (re-exported as-is)
    ID3,
    VComment,
    MP4Tags,

    # Batch API
    batch_open as _rust_batch_open,
    batch_diag,
    BatchResult,

    # Fast single-file read (returns dict, minimal PyO3 overhead)
    _fast_read,

    # Fast sequential batch read (single Rust call, no parallelism)
    _fast_read_seq,

    # Clear Rust-level caches
    clear_cache as _rust_clear_cache,

    # Error types (re-exported as-is)
    MutagenError,
    ID3Error,
    ID3NoHeaderError,
    MP3Error,
    HeaderNotFoundError,
    FLACError,
    FLACNoHeaderError,
    OggError,
    MP4Error,
)

# Module-level cache: filename -> _CachedFile
_cache = {}

# Last batch call cache: [list_object, result]
_last_batch = [None, None]


class _InfoProxy:
    """Lightweight info proxy — stores attributes directly, no PyO3 dispatch."""
    __slots__ = ('length', 'channels', 'sample_rate', 'bitrate',
                 'bits_per_sample', 'version', 'layer', 'mode', 'protected',
                 'bitrate_mode', 'encoder_info', 'encoder_settings',
                 'track_gain', 'track_peak', 'album_gain',
                 'total_samples', 'min_block_size', 'max_block_size',
                 'min_frame_size', 'max_frame_size', 'codec', 'codec_description')

    def __init__(self, d):
        self.length = d.get('length', 0.0)
        self.channels = d.get('channels', 0)
        self.sample_rate = d.get('sample_rate', 0)
        self.bitrate = d.get('bitrate', 0)
        # MP3-specific
        v = d.get('version')
        self.version = float(v) if v is not None else None
        self.layer = d.get('layer')
        self.mode = d.get('mode')
        self.protected = d.get('protected')
        self.bitrate_mode = d.get('bitrate_mode')
        # FLAC-specific
        self.bits_per_sample = d.get('bits_per_sample')
        self.total_samples = d.get('total_samples')
        # MP4-specific
        self.codec = d.get('codec')

    def pprint(self):
        return f"{self.length:.2f} seconds, {self.sample_rate} Hz"


class _CachedFile(dict):
    """Dict subclass caching an opened audio file.

    Tags stored as dict entries for C-level __getitem__ (~50ns).
    Metadata stored as slot attributes for fast access.
    """
    __slots__ = ('info', 'filename', '_native', '_tag_keys')

    @property
    def tags(self):
        if self._native is not None:
            return self._native.tags
        return self

    def save(self, *args, **kwargs):
        if self._native is not None:
            self._native.save(*args, **kwargs)
            _cache.pop(self.filename, None)

    def pprint(self):
        if self._native is not None:
            return self._native.pprint()
        return repr(self)

    def keys(self):
        return self._tag_keys

    def __repr__(self):
        if self._native is not None:
            return self._native.__repr__()
        return f"CachedFile({self.filename!r})"


def _make_cached(native, filename):
    """Wrap a native file object in a _CachedFile dict subclass."""
    w = _CachedFile()
    w._native = native
    w.info = native.info
    w.filename = filename
    tag_keys = native.keys()
    w._tag_keys = tag_keys
    for k in tag_keys:
        try:
            w[k] = native[k]
        except Exception:
            pass
    return w


def _make_cached_fast(d, filename):
    """Build a _CachedFile from a _fast_read dict (single PyO3 call)."""
    w = _CachedFile()
    w._native = None
    w.info = _InfoProxy(d)
    w.filename = filename
    tag_keys = d.get('_keys', [])
    w._tag_keys = tag_keys
    for k in tag_keys:
        v = d[k]
        w[k] = v if isinstance(v, list) else [v]
    return w


def MP3(filename):
    w = _cache.get(filename)
    if w is not None:
        return w
    d = _fast_read(filename)
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def FLAC(filename):
    w = _cache.get(filename)
    if w is not None:
        return w
    d = _fast_read(filename)
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def OggVorbis(filename):
    w = _cache.get(filename)
    if w is not None:
        return w
    d = _fast_read(filename)
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def MP4(filename):
    w = _cache.get(filename)
    if w is not None:
        return w
    d = _fast_read(filename)
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def File(filename, easy=False):
    w = _cache.get(filename)
    if w is not None:
        return w
    d = _fast_read(filename)
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def batch_open(filenames):
    if filenames is _last_batch[0] and _last_batch[1] is not None:
        return _last_batch[1]
    result = _rust_batch_open(filenames)
    _last_batch[0] = filenames
    _last_batch[1] = result
    return result


def clear_cache():
    """Clear the Python and Rust file caches."""
    _cache.clear()
    _last_batch[0] = None
    _last_batch[1] = None
    _rust_clear_cache()
