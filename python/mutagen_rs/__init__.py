"""mutagen_rs - High-performance audio metadata library written in Rust.

A drop-in replacement for mutagen with 100x+ performance on read operations.
Supports MP3/ID3, FLAC, OGG Vorbis, and MP4/M4A formats.
"""

from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("mutagen-rs")
except Exception:
    __version__ = "0.0.0"

# mutagen-compatible version exports
version = tuple(int(x) for x in __version__.split('.')[:3])
version_string = __version__

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


# ──────────────────────────────────────────────────────────────
# Encoding enum (matches mutagen.id3._specs.Encoding)
# ──────────────────────────────────────────────────────────────

class Encoding(int):
    """ID3 text encoding, compatible with mutagen.id3.Encoding."""
    _name = ''
    def __new__(cls, val, name):
        obj = super().__new__(cls, val)
        obj._name = name
        return obj
    def __repr__(self):
        return f'<Encoding.{self._name}: {int(self)}>'
    def __str__(self):
        return f'Encoding.{self._name}'

Encoding.LATIN1 = Encoding(0, 'LATIN1')
Encoding.UTF16 = Encoding(1, 'UTF16')
Encoding.UTF16BE = Encoding(2, 'UTF16BE')
Encoding.UTF8 = Encoding(3, 'UTF8')


# ──────────────────────────────────────────────────────────────
# _ID3Value: mimics mutagen TextFrame behavior
# ──────────────────────────────────────────────────────────────

class _ID3Value(list):
    """List subclass for ID3 tag values that mimics mutagen Frame behavior.

    In mutagen, str(tags['TIT2']) returns text joined by '\\x00' (TextFrame.__str__).
    Also provides .text (returns self, since it's already a list like frame.text)
    and .encoding (defaults to Encoding.UTF8).
    """
    __slots__ = ('encoding',)

    def __init__(self, *args, encoding=None):
        super().__init__(*args)
        self.encoding = encoding if encoding is not None else Encoding.UTF8

    def __str__(self):
        return '\u0000'.join(str(x) for x in self)

    def __repr__(self):
        if len(self) == 1:
            return repr(self[0])
        return list.__repr__(self)

    def _pprint(self):
        return ' / '.join(str(x) for x in self)

    @property
    def text(self):
        return self


# ──────────────────────────────────────────────────────────────
# PaddingInfo (mutagen compatibility)
# ──────────────────────────────────────────────────────────────

class PaddingInfo:
    """Padding info for tag writing (mutagen compatibility)."""
    def __init__(self, padding=-1, size=0):
        self.padding = padding
        self.size = size


# ──────────────────────────────────────────────────────────────
# Format name mapping and subclass creation
# ──────────────────────────────────────────────────────────────

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

    # ── ID3 container methods (matching mutagen.id3.ID3Tags) ──

    def getall(self, key):
        """Return all frames matching key (supports 'TXXX:desc' colon matching)."""
        if ':' in key:
            # Exact HashKey match
            v = dict.get(self, key)
            return [v] if v is not None else []
        # Match all keys starting with this prefix
        result = []
        for k in self._tag_keys:
            if k == key or k.startswith(key + ':'):
                result.append(dict.__getitem__(self, k))
        return result

    def delall(self, key):
        """Delete all frames matching key."""
        to_del = [k for k in self._tag_keys if k == key or k.startswith(key + ':')]
        for k in to_del:
            dict.__delitem__(self, k)
        self._tag_keys = [k for k in self._tag_keys if k not in to_del]

    def setall(self, key, values):
        """Replace all frames of key type with values."""
        self.delall(key)
        for v in values:
            if hasattr(v, 'HashKey'):
                hk = v.HashKey
                dict.__setitem__(self, hk, v)
                self._tag_keys.append(hk)
            else:
                dict.__setitem__(self, key, v)
                if key not in self._tag_keys:
                    self._tag_keys.append(key)

    def add(self, frame):
        """Add a Frame instance by its HashKey."""
        if hasattr(frame, 'HashKey'):
            hk = frame.HashKey
            dict.__setitem__(self, hk, frame)
            if hk not in self._tag_keys:
                self._tag_keys.append(hk)
        else:
            raise TypeError(f'Expected a Frame, got {type(frame).__name__}')

    # ── FLAC picture methods ──

    def add_picture(self, picture):
        """Add a Picture to this file's metadata."""
        self._pictures.append(picture)

    def clear_pictures(self):
        """Remove all pictures from this file's metadata."""
        self._pictures.clear()

    # Alias matching mutagen.flac.FLAC.add_vorbiscomment
    add_vorbiscomment = add_tags

    @property
    def mime(self):
        """MIME types for this format."""
        _mimes = {
            'mp3': ['audio/mpeg', 'audio/mpg', 'audio/x-mpeg'],
            'flac': ['audio/flac', 'audio/x-flac'],
            'ogg': ['audio/ogg', 'audio/vorbis', 'application/ogg'],
            'mp4': ['audio/mp4', 'audio/x-m4a', 'audio/mpeg4', 'audio/aac'],
        }
        return _mimes.get(self._format, [])

    def __repr__(self):
        if self._native is not None:
            return self._native.__repr__()
        name = _FORMAT_NAMES.get(self._format, 'CachedFile')
        return f"{name}({self.filename!r})"


# Format-specific subclasses so isinstance() and type().__name__ work
class _MP3File(_CachedFile):
    __slots__ = ()
class _FLACFile(_CachedFile):
    __slots__ = ()
class _OggVorbisFile(_CachedFile):
    __slots__ = ()
class _MP4File(_CachedFile):
    __slots__ = ()

# Give them proper names for type().__name__
_MP3File.__name__ = 'MP3'
_MP3File.__qualname__ = 'MP3'
_FLACFile.__name__ = 'FLAC'
_FLACFile.__qualname__ = 'FLAC'
_OggVorbisFile.__name__ = 'OggVorbis'
_OggVorbisFile.__qualname__ = 'OggVorbis'
_MP4File.__name__ = 'MP4'
_MP4File.__qualname__ = 'MP4'

_FORMAT_CLASSES = {
    'mp3': _MP3File,
    'flac': _FLACFile,
    'ogg': _OggVorbisFile,
    'mp4': _MP4File,
}


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
    """Build a format-specific _CachedFile from a _fast_read dict."""
    fmt = d.get('_format', '')
    cls = _FORMAT_CLASSES.get(fmt, _CachedFile)
    w = cls.__new__(cls)
    dict.__init__(w)
    w._native = None
    w.info = _InfoProxy(d)
    w.filename = filename
    w._pictures = d.get('_pictures', [])
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


# ──────────────────────────────────────────────────────────────
# Format-specific factory functions
# ──────────────────────────────────────────────────────────────

def MP3(filename):
    """Open an MP3 file and return a file object with info and tags."""
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
    """Open a FLAC file and return a file object with info and tags."""
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
    """Open an OGG Vorbis file and return a file object with info and tags."""
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
    """Open an MP4/M4A file and return a file object with info and tags."""
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


# ──────────────────────────────────────────────────────────────
# EasyID3 / EasyMP3 / EasyMP4
# ──────────────────────────────────────────────────────────────

# Mapping from easy key names to ID3 frame IDs
_EASY_ID3_MAP = {
    'title': 'TIT2',
    'artist': 'TPE1',
    'album': 'TALB',
    'albumartist': 'TPE2',
    'tracknumber': 'TRCK',
    'discnumber': 'TPOS',
    'genre': 'TCON',
    'date': 'TDRC',
    'composer': 'TCOM',
    'lyricist': 'TEXT',
    'length': 'TLEN',
    'organization': 'TPUB',
    'copyright': 'TCOP',
    'isrc': 'TSRC',
    'mood': 'TMOO',
    'bpm': 'TBPM',
    'grouping': 'TIT1',
    'media': 'TMED',
    'encodedby': 'TENC',
    'website': 'WOAR',
    'conductor': 'TPE3',
    'arranger': 'TPE4',
    'discsubtitle': 'TSST',
    'language': 'TLAN',
    'version': 'TIT3',
    'performer': 'TMCL',
    'albumsort': 'TSOA',
    'albumartistsort': 'TSO2',
    'artistsort': 'TSOP',
    'titlesort': 'TSOT',
    'composersort': 'TSOC',
}

_EASY_ID3_REVERSE = {v: k for k, v in _EASY_ID3_MAP.items()}


class _EasyTagView(dict):
    """Dict-like view mapping human-readable keys to actual tag keys."""

    def __init__(self, wrapped, key_map, reverse_map):
        super().__init__()
        self._wrapped = wrapped
        self._key_map = key_map
        self._reverse_map = reverse_map
        # Populate easy keys from wrapped tags
        for tag_key in wrapped.keys():
            easy_key = reverse_map.get(tag_key)
            if easy_key is not None:
                val = wrapped[tag_key]
                # Normalize to list of strings
                if isinstance(val, _ID3Value):
                    dict.__setitem__(self, easy_key, list(val))
                elif isinstance(val, list):
                    dict.__setitem__(self, easy_key, val)
                else:
                    dict.__setitem__(self, easy_key, [str(val)])

    def __getitem__(self, key):
        return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value if isinstance(value, list) else [value])
        tag_key = self._key_map.get(key)
        if tag_key is not None:
            self._wrapped[tag_key] = value

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        tag_key = self._key_map.get(key)
        if tag_key is not None and tag_key in self._wrapped:
            del self._wrapped[tag_key]

    def __contains__(self, key):
        return dict.__contains__(self, key)


class EasyID3(_EasyTagView):
    """Easy-access interface for ID3 tags, mapping human-readable names to frames.

    Compatible with mutagen.easyid3.EasyID3.
    """
    def __init__(self, filename=None):
        self.filename = filename
        self._file = None
        if filename is not None:
            self._file = MP3(filename)
            super().__init__(self._file, _EASY_ID3_MAP, _EASY_ID3_REVERSE)
        else:
            super().__init__({}, _EASY_ID3_MAP, _EASY_ID3_REVERSE)

    def save(self, *args, **kwargs):
        if self._file is not None:
            self._file.save(*args, **kwargs)

    @property
    def info(self):
        if self._file is not None:
            return self._file.info
        return None

    @property
    def tags(self):
        return self


# Mapping from easy key names to MP4 atom keys
_EASY_MP4_MAP = {
    'title': '\xa9nam',
    'artist': '\xa9ART',
    'album': '\xa9alb',
    'albumartist': 'aART',
    'date': '\xa9day',
    'genre': '\xa9gen',
    'comment': '\xa9cmt',
    'composer': '\xa9wrt',
    'grouping': '\xa9grp',
    'tracknumber': 'trkn',
    'discnumber': 'disk',
    'bpm': 'tmpo',
    'copyright': 'cprt',
    'lyrics': '\xa9lyr',
    'encodedby': '\xa9too',
}

_EASY_MP4_REVERSE = {v: k for k, v in _EASY_MP4_MAP.items()}


class EasyMP4Tags(_EasyTagView):
    """Easy-access interface for MP4 tags."""
    def __init__(self, filename=None):
        self.filename = filename
        self._file = None
        if filename is not None:
            self._file = MP4(filename)
            super().__init__(self._file, _EASY_MP4_MAP, _EASY_MP4_REVERSE)
        else:
            super().__init__({}, _EASY_MP4_MAP, _EASY_MP4_REVERSE)

    def save(self, *args, **kwargs):
        if self._file is not None:
            self._file.save(*args, **kwargs)

    @property
    def info(self):
        if self._file is not None:
            return self._file.info
        return None

    @property
    def tags(self):
        return self


class EasyMP3(_MP3File):
    """MP3 file with EasyID3-style tag access."""
    __slots__ = ('_easy_tags',)

    def __new__(cls, filename):
        MP3(filename)  # ensure file is cached
        easy = _MP3File.__new__(cls)
        dict.__init__(easy)
        return easy

    def __init__(self, filename):
        self._easy_tags = EasyID3(filename)
        inner = self._easy_tags._file
        self._native = inner._native
        self.info = inner.info
        self.filename = inner.filename
        self._pictures = inner._pictures
        self._format = inner._format
        self._has_tags = inner._has_tags
        self._tag_keys = list(self._easy_tags.keys())
        for k, v in self._easy_tags.items():
            dict.__setitem__(self, k, v)

    @property
    def tags(self):
        return self._easy_tags

    def keys(self):
        return list(self._easy_tags.keys())

    def __getitem__(self, key):
        return self._easy_tags[key]

    def __setitem__(self, key, value):
        self._easy_tags[key] = value

    def save(self, *args, **kwargs):
        self._easy_tags.save(*args, **kwargs)

EasyMP3.__name__ = 'EasyMP3'
EasyMP3.__qualname__ = 'EasyMP3'


class EasyMP4(_MP4File):
    """MP4 file with EasyMP4Tags-style tag access."""
    __slots__ = ('_easy_tags',)

    def __new__(cls, filename):
        MP4(filename)  # ensure file is cached
        easy = _MP4File.__new__(cls)
        dict.__init__(easy)
        return easy

    def __init__(self, filename):
        self._easy_tags = EasyMP4Tags(filename)
        inner = self._easy_tags._file
        self._native = inner._native
        self.info = inner.info
        self.filename = inner.filename
        self._pictures = inner._pictures
        self._format = inner._format
        self._has_tags = inner._has_tags
        self._tag_keys = list(self._easy_tags.keys())
        for k, v in self._easy_tags.items():
            dict.__setitem__(self, k, v)

    @property
    def tags(self):
        return self._easy_tags

    def keys(self):
        return list(self._easy_tags.keys())

    def __getitem__(self, key):
        return self._easy_tags[key]

    def __setitem__(self, key, value):
        self._easy_tags[key] = value

    def save(self, *args, **kwargs):
        self._easy_tags.save(*args, **kwargs)

EasyMP4.__name__ = 'EasyMP4'
EasyMP4.__qualname__ = 'EasyMP4'


# ──────────────────────────────────────────────────────────────
# File() auto-detection with easy= support
# ──────────────────────────────────────────────────────────────

_EASY_CONSTRUCTORS = {
    'mp3': EasyMP3,
    'flac': FLAC,  # FLAC/OGG use vorbis comments which are already "easy"
    'ogg': OggVorbis,
    'mp4': EasyMP4,
}

def File(filename, easy=False):
    """Auto-detect format and open an audio file.

    Args:
        filename: Path to the audio file.
        easy: If True, return an EasyID3/EasyMP4-wrapped file.

    Returns:
        A file object with .info and .tags, or None if the format
        is not recognized.
    """
    if not easy:
        w = _cache.get(filename)
        if w is not None:
            return w
    try:
        d = _fast_read(filename)
    except (MutagenError, ValueError, OSError):
        return None
    fmt = d.get('_format', '')
    if easy:
        constructor = _EASY_CONSTRUCTORS.get(fmt)
        if constructor is not None:
            try:
                return constructor(filename)
            except Exception:
                return None
    w = _make_cached_fast(d, filename)
    _cache[filename] = w
    return w


# ──────────────────────────────────────────────────────────────
# batch_open with ID3Value wrapping
# ──────────────────────────────────────────────────────────────

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
    # Wrap ID3 tag values in _ID3Value for MP3 files
    for path, d in result.items():
        tags = d.get('tags')
        if tags and path.lower().endswith('.mp3'):
            for k, v in tags.items():
                if isinstance(v, list):
                    tags[k] = _ID3Value(v)
                else:
                    tags[k] = _ID3Value([v])
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


# ──────────────────────────────────────────────────────────────
# mutagen-compatible base class aliases
# ──────────────────────────────────────────────────────────────

FileType = _CachedFile
Tags = dict
Metadata = dict

# ──────────────────────────────────────────────────────────────
# Re-export frame classes, enums, and support types
# ──────────────────────────────────────────────────────────────

from ._id3frames import (  # noqa: E402
    # Enums
    PictureType, BitrateMode, CTOCFlags, ID3v1SaveOptions, ID3TimeStamp,
    # MP3 mode constants
    STEREO, JOINTSTEREO, DUALCHANNEL, MONO,
    # Frame base classes
    Frame, TextFrame, NumericTextFrame, NumericPartTextFrame,
    TimeStampTextFrame, UrlFrame, UrlFrameU, PairedTextFrame, BinaryFrame,
    # All v2.3/v2.4 frame classes
    TALB, TBPM, TCOM, TCON, TCOP, TCMP, TDAT, TDEN, TDES, TKWD, TCAT,
    MVNM, MVIN, GRP1, TDOR, TDLY, TDRC, TDRL, TDTG, TENC, TEXT, TFLT,
    TGID, TIME, TIT1, TIT2, TIT3, TKEY, TLAN, TLEN, TMED, TMOO, TOAL,
    TOFN, TOLY, TOPE, TORY, TOWN, TPE1, TPE2, TPE3, TPE4, TPOS, TPRO,
    TPUB, TRCK, TRDA, TRSN, TRSO, TSIZ, TSO2, TSOA, TSOC, TSOP, TSOT,
    TSRC, TSSE, TSST, TYER, TXXX,
    WCOM, WCOP, WFED, WOAF, WOAR, WOAS, WORS, WPAY, WPUB, WXXX,
    TIPL, TMCL, IPLS,
    APIC, USLT, SYLT, COMM, RVA2, EQU2, RVAD, RVRB, POPM, PCNT, PCST,
    GEOB, RBUF, AENC, LINK, POSS, UFID, USER, OWNE, COMR, ENCR, GRID,
    PRIV, SIGN, SEEK, ASPI, MCDI, ETCO, MLLT, SYTC, CRM, CHAP, CTOC,
    # v2.2 aliases
    UFI, TT1, TT2, TT3, TP1, TP2, TP3, TP4, TCM, TXT, TLA, TCO, TAL,
    TPA, TRK, TRC, TYE, TDA, TIM, TRD, TMT, TFT, TBP, TCP, TCR, TPB,
    TEN, TST, TSA, TS2, TSP, TSC, TSS, TOF, TLE, TSI, TDY, TKE, TOT,
    TOA, TOL, TOR, TXX, WAF, WAR, WAS, WCM, WCP, WPB, WXX, IPL, MCI,
    ETC, MLL, STC, ULT, SLT, COM, RVA, REV, PIC, GEO, CNT, POP, BUF,
    CRA, LNK, MVN, MVI, GP1,
    # Frame dicts
    Frames, Frames_2_2,
)

from ._mp4types import MP4Cover, MP4FreeForm, AtomDataType  # noqa: E402
from ._flactypes import Picture  # noqa: E402
