"""mutagen_rs - High-performance audio metadata library written in Rust.

A drop-in replacement for mutagen with 100x+ performance on read operations.
Supports MP3/ID3, FLAC, OGG Vorbis, and MP4/M4A formats.
"""

from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("mutagen-rs")
except Exception:
    __version__ = "0.0.0"

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

    # Fast info-only read (no tags, maximum speed)
    _fast_info,

    # Fast sequential batch read (single Rust call, no parallelism)
    _fast_read_seq,

    # Fast parallel batch read (rayon + raw FFI dict creation)
    _fast_batch_read,

    # Clear Rust-level caches
    clear_cache as _rust_clear_cache,
    clear_all_caches as _rust_clear_all_caches,

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


class _ID3Value(list):
    """List subclass for ID3 tag values that mimics mutagen Frame str() behavior.

    In mutagen, str(tags['TIT2']) returns the text value joined by '/'.
    Plain Python lists return "['text']" which breaks drop-in compatibility.
    This class ensures str() returns the text directly, like mutagen does.
    """
    __slots__ = ()

    def __str__(self):
        return '/'.join(str(x) for x in self)

    def __repr__(self):
        if len(self) == 1:
            return repr(self[0])
        return list.__repr__(self)


# Format name mapping for _CachedFile type representation
_FORMAT_NAMES = {'mp3': 'MP3', 'flac': 'FLAC', 'ogg': 'OggVorbis', 'mp4': 'MP4'}


class _InfoProxy:
    """Lightweight info proxy -- stores attributes directly, no PyO3 dispatch."""
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
    __slots__ = ('info', 'filename', '_native', '_tag_keys', '_pictures',
                 '_format', '_has_tags')

    @property
    def tags(self):
        """Return the tag dict, or None if no tags exist (matching mutagen)."""
        if self._native is not None:
            return self._native.tags
        # For MP3: return None when no ID3 header was found (matching mutagen)
        if not self._has_tags:
            return None
        return self

    @property
    def pictures(self):
        """FLAC pictures (list of dicts with type, mime, desc, width, height, data)."""
        if self._native is not None and hasattr(self._native, 'pictures'):
            return self._native.pictures
        return getattr(self, '_pictures', [])

    def _get_native(self):
        """Get or create a native Rust object for mutation operations."""
        if self._native is not None:
            return self._native
        ext = self.filename.rsplit('.', 1)[-1].lower()
        if ext == 'mp3':
            return _RustMP3(self.filename)
        elif ext == 'flac':
            return _RustFLAC(self.filename)
        elif ext == 'ogg':
            return _RustOggVorbis(self.filename)
        elif ext in ('m4a', 'mp4', 'aac'):
            return _RustMP4(self.filename)
        raise NotImplementedError(f"Not supported for .{ext}")

    def save(self, *args, **kwargs):
        """Save tag changes to the file."""
        if self._native is not None:
            self._native.save(*args, **kwargs)
            _cache.pop(self.filename, None)
            _rust_clear_cache()
            return
        native = self._get_native()
        for k in dict.keys(self):
            v = dict.__getitem__(self, k)
            if v is not None:
                native[k] = v
        native.save(*args, **kwargs)
        _cache.pop(self.filename, None)
        _rust_clear_cache()

    def delete(self):
        """Delete all tags from the file."""
        native = self._get_native()
        native.delete()
        _cache.pop(self.filename, None)
        _rust_clear_cache()

    def add_tags(self):
        """Ensure tag container exists."""
        if self._native is not None and hasattr(self._native, 'add_tags'):
            self._native.add_tags()

    def clear(self):
        """Remove all tags from memory (does not write to file)."""
        dict.clear(self)
        self._tag_keys = []
        if self._native is not None and hasattr(self._native, 'clear'):
            self._native.clear()

    def pprint(self):
        """Pretty-print file info and tags."""
        if self._native is not None:
            return self._native.pprint()
        return repr(self)

    def keys(self):
        """Return list of tag keys."""
        return self._tag_keys

    def __repr__(self):
        if self._native is not None:
            return self._native.__repr__()
        name = _FORMAT_NAMES.get(self._format, 'CachedFile')
        return f"{name}({self.filename!r})"


def _make_cached(native, filename):
    """Wrap a native file object in a _CachedFile dict subclass."""
    w = _CachedFile()
    w._native = native
    w.info = native.info
    w.filename = filename
    w._pictures = []
    w._format = ''
    w._has_tags = True
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
    w._pictures = d.get('_pictures', [])
    fmt = d.get('_format', '')
    w._format = fmt
    w._has_tags = d.get('_has_tags', True)
    tag_keys = d.get('_keys', [])
    w._tag_keys = tag_keys
    # ID3 formats (mp3) use _ID3Value so str() returns text, not "['text']"
    is_id3 = (fmt == 'mp3')
    for k in tag_keys:
        v = d[k]
        if isinstance(v, list):
            w[k] = _ID3Value(v) if is_id3 else v
        else:
            w[k] = _ID3Value([v]) if is_id3 else [v]
    return w


def MP3(filename):
    """Open an MP3 file and return a file object with info and tags.

    Args:
        filename: Path to the MP3 file.

    Returns:
        A file object with .info (MPEGInfo), .tags (dict of ID3 frames),
        and dict-like tag access.

    Raises:
        MutagenError: If the file cannot be parsed.
    """
    w = _cache.get(filename)
    if w is not None:
        return w
    try:
        d = _fast_read(filename)
    except (ValueError, OSError) as e:
        raise MutagenError(str(e)) from None
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def FLAC(filename):
    """Open a FLAC file and return a file object with info and tags.

    Args:
        filename: Path to the FLAC file.

    Returns:
        A file object with .info (StreamInfo), .tags (VorbisComment dict),
        .pictures, and dict-like tag access.

    Raises:
        MutagenError: If the file cannot be parsed.
    """
    w = _cache.get(filename)
    if w is not None:
        return w
    try:
        d = _fast_read(filename)
    except (ValueError, OSError) as e:
        raise MutagenError(str(e)) from None
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def OggVorbis(filename):
    """Open an OGG Vorbis file and return a file object with info and tags.

    Args:
        filename: Path to the OGG file.

    Returns:
        A file object with .info (OggVorbisInfo), .tags (VorbisComment dict),
        and dict-like tag access.

    Raises:
        MutagenError: If the file cannot be parsed.
    """
    w = _cache.get(filename)
    if w is not None:
        return w
    try:
        d = _fast_read(filename)
    except (ValueError, OSError) as e:
        raise MutagenError(str(e)) from None
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def MP4(filename):
    """Open an MP4/M4A file and return a file object with info and tags.

    Args:
        filename: Path to the MP4/M4A file.

    Returns:
        A file object with .info (MP4Info), .tags (MP4Tags dict),
        and dict-like tag access.

    Raises:
        MutagenError: If the file cannot be parsed.
    """
    w = _cache.get(filename)
    if w is not None:
        return w
    try:
        d = _fast_read(filename)
    except (ValueError, OSError) as e:
        raise MutagenError(str(e)) from None
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def File(filename, easy=False):
    """Auto-detect format and open an audio file.

    Args:
        filename: Path to the audio file.
        easy: Ignored (for mutagen API compatibility).

    Returns:
        A file object with .info and .tags, or None if the format
        is not recognized.
    """
    w = _cache.get(filename)
    if w is not None:
        return w
    try:
        d = _fast_read(filename)
    except (MutagenError, ValueError, OSError):
        return None
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


def batch_open(filenames):
    """Open multiple audio files in parallel using Rust I/O.

    Args:
        filenames: List of file paths to open.

    Returns:
        A dict mapping filepath -> result dict with 'tags', 'length',
        'sample_rate', 'channels', etc.
    """
    if filenames is _last_batch[0] and _last_batch[1] is not None:
        return _last_batch[1]
    result = _rust_batch_open(filenames)
    _last_batch[0] = filenames
    _last_batch[1] = result
    return result


def clear_cache():
    """Clear the Python and Rust result caches."""
    _cache.clear()
    _last_batch[0] = None
    _last_batch[1] = None
    _rust_clear_cache()


def clear_all_caches():
    """Clear ALL caches including raw file data and templates."""
    _cache.clear()
    _last_batch[0] = None
    _last_batch[1] = None
    _rust_clear_all_caches()
