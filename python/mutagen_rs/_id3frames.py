"""ID3 frame classes and support types for mutagen API compatibility.

Provides constructable Frame subclasses matching mutagen.id3._frames,
plus enums (PictureType, BitrateMode, CTOCFlags, ID3v1SaveOptions)
and ID3TimeStamp.
"""

import functools


# ──────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────

def _make_int_enum(name, members):
    """Create a simple int-enum class with named members."""
    ns = {}
    for mname, mval in members:
        ns[mname] = mval

    class EnumMeta(type):
        def __iter__(cls):
            return iter(cls._members.values())
        def __contains__(cls, item):
            return item in cls._members.values()

    class IntEnum(int, metaclass=EnumMeta):
        _name = ''
        _members = {}
        def __new__(cls, val, mname=None):
            obj = int.__new__(cls, val)
            obj._name = mname or ''
            return obj
        def __repr__(self):
            return f'<{name}.{self._name}: {int(self)}>'
        def __str__(self):
            return f'{name}.{self._name}'

    IntEnum.__name__ = name
    IntEnum.__qualname__ = name
    member_dict = {}
    for mname, mval in members:
        inst = IntEnum(mval, mname)
        setattr(IntEnum, mname, inst)
        member_dict[mname] = inst
    IntEnum._members = member_dict
    return IntEnum


PictureType = _make_int_enum('PictureType', [
    ('OTHER', 0), ('FILE_ICON', 1), ('OTHER_FILE_ICON', 2),
    ('COVER_FRONT', 3), ('COVER_BACK', 4), ('LEAFLET_PAGE', 5),
    ('MEDIA', 6), ('LEAD_ARTIST', 7), ('ARTIST', 8),
    ('CONDUCTOR', 9), ('BAND', 10), ('COMPOSER', 11),
    ('LYRICIST', 12), ('RECORDING_LOCATION', 13),
    ('DURING_RECORDING', 14), ('DURING_PERFORMANCE', 15),
    ('SCREEN_CAPTURE', 16), ('FISH', 17), ('ILLUSTRATION', 18),
    ('BAND_LOGOTYPE', 19), ('PUBLISHER_LOGOTYPE', 20),
])

BitrateMode = _make_int_enum('BitrateMode', [
    ('UNKNOWN', 0), ('CBR', 1), ('VBR', 2), ('ABR', 3),
])

CTOCFlags = _make_int_enum('CTOCFlags', [
    ('TOP_LEVEL', 2), ('ORDERED', 1),
])

ID3v1SaveOptions = _make_int_enum('ID3v1SaveOptions', [
    ('REMOVE', 0), ('UPDATE', 1), ('CREATE', 2),
])

# MP3 mode constants
STEREO = 0
JOINTSTEREO = 1
DUALCHANNEL = 2
MONO = 3


# ──────────────────────────────────────────────────────────────
# ID3TimeStamp
# ──────────────────────────────────────────────────────────────

@functools.total_ordering
class ID3TimeStamp:
    """Represents an ID3v2.4 timestamp (e.g. '2024-01-15T12:30:00')."""

    def __init__(self, text=''):
        self.text = str(text)

    @property
    def year(self):
        try:
            return int(self.text[:4])
        except (ValueError, IndexError):
            return None

    @property
    def month(self):
        try:
            return int(self.text[5:7])
        except (ValueError, IndexError):
            return None

    @property
    def day(self):
        try:
            return int(self.text[8:10])
        except (ValueError, IndexError):
            return None

    @property
    def hour(self):
        try:
            return int(self.text[11:13])
        except (ValueError, IndexError):
            return None

    @property
    def minute(self):
        try:
            return int(self.text[14:16])
        except (ValueError, IndexError):
            return None

    @property
    def second(self):
        try:
            return int(self.text[17:19])
        except (ValueError, IndexError):
            return None

    def __str__(self):
        return self.text

    def __repr__(self):
        return f'{self.text!r}'

    def __eq__(self, other):
        if isinstance(other, ID3TimeStamp):
            return self.text == other.text
        return self.text == str(other)

    def __lt__(self, other):
        if isinstance(other, ID3TimeStamp):
            return self.text < other.text
        return NotImplemented

    def __hash__(self):
        return hash(self.text)

    def encode(self, *args):
        return self.text.encode('utf-8')


# ──────────────────────────────────────────────────────────────
# Encoding (re-exported from __init__, but also importable here)
# ──────────────────────────────────────────────────────────────

class Encoding(int):
    """ID3 text encoding, compatible with mutagen.id3.Encoding."""
    _name = ''
    def __new__(cls, val, name=''):
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
# Frame base classes
# ──────────────────────────────────────────────────────────────

class Frame:
    """Base ID3 frame, matching mutagen.id3.Frame interface."""

    # Subclasses define _framespec as list of (attr_name, default_value) tuples
    _framespec = []
    _optionalspec = []

    def __init__(self, *args, **kwargs):
        # Set defaults from spec
        for attr, default in self._framespec + self._optionalspec:
            setattr(self, attr, default)
        # Positional args fill spec in order
        specs = self._framespec + self._optionalspec
        for i, val in enumerate(args):
            if i < len(specs):
                setattr(self, specs[i][0], val)
        # Keyword args override
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def FrameID(self):
        return type(self).__name__

    @property
    def HashKey(self):
        return self.FrameID

    def _pprint(self):
        return str(self)

    def pprint(self):
        return f'{self.FrameID}={self._pprint()}'

    def __repr__(self):
        return f'{self.FrameID}({self._pprint()!r})'

    def __eq__(self, other):
        if not isinstance(other, Frame):
            return NotImplemented
        return self.HashKey == other.HashKey

    __hash__ = None


class TextFrame(Frame):
    """Text string frame (most ID3 text frames inherit from this)."""

    _framespec = [('encoding', Encoding.UTF8), ('text', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.text is None:
            self.text = []
        elif isinstance(self.text, str):
            self.text = [self.text]

    def __str__(self):
        return '\u0000'.join(str(x) for x in self.text)

    def __bytes__(self):
        return str(self).encode('utf-8')

    def __eq__(self, other):
        if isinstance(other, str):
            return str(self) == other
        if isinstance(other, bytes):
            return bytes(self) == other
        if isinstance(other, TextFrame):
            return self.text == other.text
        return NotImplemented

    def __getitem__(self, item):
        return self.text[item]

    def __iter__(self):
        return iter(self.text)

    def __len__(self):
        return len(self.text)

    def __contains__(self, item):
        return item in self.text

    def append(self, value):
        self.text.append(value)

    def extend(self, values):
        self.text.extend(values)

    def _pprint(self):
        return ' / '.join(str(x) for x in self.text)

    def __repr__(self):
        return f'{self.FrameID}(encoding={self.encoding!r}, text={self.text!r})'


class NumericTextFrame(TextFrame):
    """Numeric text frame."""
    def __pos__(self):
        return int(self.text[0])


class NumericPartTextFrame(TextFrame):
    """Numeric text with possible '/' separator (e.g. track 3/12)."""
    def __pos__(self):
        return int(self.text[0].split('/')[0])


class TimeStampTextFrame(TextFrame):
    """Text frame with ID3TimeStamp values."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert string timestamps to ID3TimeStamp objects
        self.text = [
            v if isinstance(v, ID3TimeStamp) else ID3TimeStamp(str(v))
            for v in self.text
        ]


class UrlFrame(Frame):
    """URL frame."""
    _framespec = [('url', '')]

    def __str__(self):
        return self.url

    def _pprint(self):
        return self.url

    def __eq__(self, other):
        if isinstance(other, str):
            return self.url == other
        if isinstance(other, UrlFrame):
            return self.url == other.url
        return NotImplemented


class UrlFrameU(UrlFrame):
    """URL frame with URL in HashKey."""
    @property
    def HashKey(self):
        return f'{self.FrameID}:{self.url}'


class PairedTextFrame(Frame):
    """Frame with list of [role, person] pairs."""
    _framespec = [('encoding', Encoding.UTF8), ('people', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.people is None:
            self.people = []

    def _pprint(self):
        return '\n'.join(f'{role}={person}' for role, person in self.people)


class BinaryFrame(Frame):
    """Frame containing binary data."""
    _framespec = [('data', b'')]

    def _pprint(self):
        return f'{len(self.data)} bytes'


# ──────────────────────────────────────────────────────────────
# Text frame subclasses (v2.3/v2.4, 4-char names)
# ──────────────────────────────────────────────────────────────

def _text(name, doc='', base=TextFrame):
    """Create a simple TextFrame subclass."""
    cls = type(name, (base,), {'__doc__': doc})
    return cls


# Standard text frames
TALB = _text('TALB', 'Album')
TBPM = _text('TBPM', 'Beats per minute', NumericTextFrame)
TCOM = _text('TCOM', 'Composer')
TCOP = _text('TCOP', 'Copyright')
TCMP = _text('TCMP', 'iTunes Compilation Flag', NumericTextFrame)
TDAT = _text('TDAT', 'Date of recording (DDMM)')
TDEN = _text('TDEN', 'Encoding Time', TimeStampTextFrame)
TDES = _text('TDES', 'iTunes Podcast Description')
TKWD = _text('TKWD', 'iTunes Podcast Keywords')
TCAT = _text('TCAT', 'iTunes Podcast Category')
MVNM = _text('MVNM', 'iTunes Movement Name')
MVIN = _text('MVIN', 'iTunes Movement Number/Count', NumericPartTextFrame)
GRP1 = _text('GRP1', 'iTunes Grouping')
TDOR = _text('TDOR', 'Original Release Time', TimeStampTextFrame)
TDLY = _text('TDLY', 'Audio Delay (ms)', NumericTextFrame)
TDRC = _text('TDRC', 'Recording Time', TimeStampTextFrame)
TDRL = _text('TDRL', 'Release Time', TimeStampTextFrame)
TDTG = _text('TDTG', 'Tagging Time', TimeStampTextFrame)
TENC = _text('TENC', 'Encoder')
TEXT = _text('TEXT', 'Lyricist')
TFLT = _text('TFLT', 'File type')
TGID = _text('TGID', 'iTunes Podcast Identifier')
TIME = _text('TIME', 'Time of recording (HHMM)')
TIT1 = _text('TIT1', 'Content group description')
TIT2 = _text('TIT2', 'Title')
TIT3 = _text('TIT3', 'Subtitle/Description refinement')
TKEY = _text('TKEY', 'Starting Key')
TLAN = _text('TLAN', 'Audio Languages')
TLEN = _text('TLEN', 'Audio Length (ms)', NumericTextFrame)
TMED = _text('TMED', 'Source Media Type')
TMOO = _text('TMOO', 'Mood')
TOAL = _text('TOAL', 'Original Album')
TOFN = _text('TOFN', 'Original Filename')
TOLY = _text('TOLY', 'Original Lyricist')
TOPE = _text('TOPE', 'Original Artist/Performer')
TORY = _text('TORY', 'Original Release Year', NumericTextFrame)
TOWN = _text('TOWN', 'Owner/Licensee')
TPE1 = _text('TPE1', 'Lead Artist/Performer')
TPE2 = _text('TPE2', 'Band/Orchestra')
TPE3 = _text('TPE3', 'Conductor')
TPE4 = _text('TPE4', 'Interpreter/Remixer')
TPOS = _text('TPOS', 'Part of set', NumericPartTextFrame)
TPRO = _text('TPRO', 'Produced (P)')
TPUB = _text('TPUB', 'Publisher')
TRCK = _text('TRCK', 'Track Number', NumericPartTextFrame)
TRDA = _text('TRDA', 'Recording Dates')
TRSN = _text('TRSN', 'Internet Radio Station Name')
TRSO = _text('TRSO', 'Internet Radio Station Owner')
TSIZ = _text('TSIZ', 'Size of audio data', NumericTextFrame)
TSO2 = _text('TSO2', 'iTunes Album Artist Sort')
TSOA = _text('TSOA', 'Album Sort Order key')
TSOC = _text('TSOC', 'iTunes Composer Sort')
TSOP = _text('TSOP', 'Performer Sort Order key')
TSOT = _text('TSOT', 'Title Sort Order key')
TSRC = _text('TSRC', 'ISRC')
TSSE = _text('TSSE', 'Encoder settings')
TSST = _text('TSST', 'Set Subtitle')
TYER = _text('TYER', 'Year of recording', NumericTextFrame)


class TCON(TextFrame):
    """Content type/Genre."""
    @property
    def genres(self):
        return list(self.text)
    @genres.setter
    def genres(self, value):
        self.text = list(value)
    def _pprint(self):
        return ' / '.join(self.genres)


# User-defined text
class TXXX(TextFrame):
    """User-defined text."""
    _framespec = [('encoding', Encoding.UTF8), ('desc', ''), ('text', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def HashKey(self):
        return f'TXXX:{self.desc}'

    def _pprint(self):
        return f'{self.desc}={" / ".join(str(x) for x in self.text)}'


# ──────────────────────────────────────────────────────────────
# URL frames
# ──────────────────────────────────────────────────────────────

class WCOM(UrlFrameU):
    """Commercial Information."""
class WCOP(UrlFrame):
    """Copyright Information."""
class WFED(UrlFrame):
    """iTunes Podcast Feed."""
class WOAF(UrlFrame):
    """Official File Information."""
class WOAR(UrlFrameU):
    """Official Artist/Performer."""
class WOAS(UrlFrame):
    """Official Source Information."""
class WORS(UrlFrame):
    """Official Internet Radio."""
class WPAY(UrlFrame):
    """Payment Information."""
class WPUB(UrlFrame):
    """Official Publisher."""


class WXXX(UrlFrame):
    """User-defined URL."""
    _framespec = [('encoding', Encoding.UTF8), ('desc', ''), ('url', '')]

    @property
    def HashKey(self):
        return f'WXXX:{self.desc}'

    def _pprint(self):
        return f'{self.desc}={self.url}'


# ──────────────────────────────────────────────────────────────
# Paired text frames
# ──────────────────────────────────────────────────────────────

class TIPL(PairedTextFrame):
    """Involved People List."""
class TMCL(PairedTextFrame):
    """Musicians Credits List."""
class IPLS(TIPL):
    """Involved People List (v2.3)."""


# ──────────────────────────────────────────────────────────────
# Complex frames
# ──────────────────────────────────────────────────────────────

class APIC(Frame):
    """Attached Picture."""
    _framespec = [
        ('encoding', Encoding.UTF8), ('mime', 'image/jpeg'),
        ('type', PictureType.COVER_FRONT), ('desc', ''), ('data', b''),
    ]

    @property
    def HashKey(self):
        return f'APIC:{self.desc}'

    def _pprint(self):
        return f'{self.desc} ({self.mime}, {len(self.data)} bytes, type {int(self.type)})'


class USLT(Frame):
    """Unsynchronised lyrics."""
    _framespec = [
        ('encoding', Encoding.UTF8), ('lang', 'eng'), ('desc', ''), ('text', ''),
    ]

    @property
    def HashKey(self):
        return f'USLT:{self.desc}:{self.lang}'

    def __str__(self):
        return self.text

    def __eq__(self, other):
        if isinstance(other, str):
            return self.text == other
        return NotImplemented

    def _pprint(self):
        return self.text[:50]


class SYLT(Frame):
    """Synchronised lyrics."""
    _framespec = [
        ('encoding', Encoding.UTF8), ('lang', 'eng'), ('format', 2),
        ('type', 1), ('desc', ''), ('text', None),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.text is None:
            self.text = []

    @property
    def HashKey(self):
        return f'SYLT:{self.desc}:{self.lang}'


class COMM(TextFrame):
    """Comment."""
    _framespec = [
        ('encoding', Encoding.UTF8), ('lang', 'eng'), ('desc', ''), ('text', None),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def HashKey(self):
        return f'COMM:{self.desc}:{self.lang}'

    def _pprint(self):
        return f'{self.desc}={" / ".join(str(x) for x in self.text)}'


class RVA2(Frame):
    """Relative volume adjustment."""
    _framespec = [('desc', ''), ('channel', 1), ('gain', 0.0), ('peak', 0.0)]

    @property
    def HashKey(self):
        return f'RVA2:{self.desc}'

    def _pprint(self):
        return f'{self.desc}: {self.gain:+.2f} dB'


class EQU2(Frame):
    """Equalisation."""
    _framespec = [('method', 0), ('desc', ''), ('adjustments', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.adjustments is None:
            self.adjustments = []

    @property
    def HashKey(self):
        return f'EQU2:{self.desc}'


class RVAD(Frame):
    """Relative volume adjustment (v2.3)."""
    _framespec = [('adjustments', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.adjustments is None:
            self.adjustments = []


class RVRB(Frame):
    """Reverb."""
    _framespec = [
        ('left', 0), ('right', 0), ('bounce_left', 0), ('bounce_right', 0),
        ('feedback_ltl', 0), ('feedback_ltr', 0), ('feedback_rtr', 0),
        ('feedback_rtl', 0), ('premix_ltr', 0), ('premix_rtl', 0),
    ]


class POPM(Frame):
    """Popularimeter."""
    _framespec = [('email', ''), ('rating', 0)]
    _optionalspec = [('count', 0)]

    @property
    def HashKey(self):
        return f'POPM:{self.email}'

    def __pos__(self):
        return self.rating

    def _pprint(self):
        return f'{self.email}: rating={self.rating}'


class PCNT(Frame):
    """Play counter."""
    _framespec = [('count', 0)]

    def __pos__(self):
        return self.count


class PCST(Frame):
    """iTunes Podcast Flag."""
    _framespec = [('value', 0)]

    def __pos__(self):
        return self.value


class GEOB(Frame):
    """General Encapsulated Object."""
    _framespec = [
        ('encoding', Encoding.UTF8), ('mime', ''), ('filename', ''),
        ('desc', ''), ('data', b''),
    ]

    @property
    def HashKey(self):
        return f'GEOB:{self.desc}'


class RBUF(Frame):
    """Recommended buffer size."""
    _framespec = [('size', 0)]
    _optionalspec = [('info', 0), ('offset', 0)]


class AENC(Frame):
    """Audio encryption."""
    _framespec = [('owner', ''), ('preview_start', 0), ('preview_length', 0), ('data', b'')]

    @property
    def HashKey(self):
        return f'AENC:{self.owner}'


class LINK(Frame):
    """Linked information."""
    _framespec = [('frameid', ''), ('url', ''), ('data', b'')]

    @property
    def HashKey(self):
        return f'LINK:{self.frameid}:{self.url}:{self.data!r}'


class POSS(Frame):
    """Position synchronisation."""
    _framespec = [('format', 2), ('position', 0)]


class UFID(Frame):
    """Unique file identifier."""
    _framespec = [('owner', ''), ('data', b'')]

    @property
    def HashKey(self):
        return f'UFID:{self.owner}'


class USER(Frame):
    """Terms of use."""
    _framespec = [('encoding', Encoding.UTF8), ('lang', 'eng'), ('text', '')]

    @property
    def HashKey(self):
        return f'USER:{self.lang}'

    def __str__(self):
        return self.text


class OWNE(Frame):
    """Ownership."""
    _framespec = [('encoding', Encoding.UTF8), ('price', ''), ('date', ''), ('seller', '')]


class COMR(Frame):
    """Commercial."""
    _framespec = [
        ('encoding', Encoding.UTF8), ('price', ''), ('valid_until', ''),
        ('contact', ''), ('format', 0), ('seller', ''), ('desc', ''),
    ]
    _optionalspec = [('mime', ''), ('logo', b'')]


class ENCR(Frame):
    """Encryption method registration."""
    _framespec = [('owner', ''), ('method', 0), ('data', b'')]

    @property
    def HashKey(self):
        return f'ENCR:{self.owner}'


class GRID(Frame):
    """Group identification."""
    _framespec = [('owner', ''), ('group', 0), ('data', b'')]

    @property
    def HashKey(self):
        return f'GRID:{self.group}'


class PRIV(Frame):
    """Private frame."""
    _framespec = [('owner', ''), ('data', b'')]

    @property
    def HashKey(self):
        return f'PRIV:{self.owner}:{self.data!r}'


class SIGN(Frame):
    """Signature."""
    _framespec = [('group', 0), ('sig', b'')]

    @property
    def HashKey(self):
        return f'SIGN:{self.group}:{self.sig!r}'


class SEEK(Frame):
    """Seek."""
    _framespec = [('offset', 0)]


class ASPI(Frame):
    """Audio seek point index."""
    _framespec = [('S', 0), ('L', 0), ('N', 0), ('b', 0), ('Fi', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.Fi is None:
            self.Fi = []


class MCDI(BinaryFrame):
    """Binary dump of CD's TOC."""


class ETCO(Frame):
    """Event timing codes."""
    _framespec = [('format', 2), ('events', None)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.events is None:
            self.events = []


class MLLT(Frame):
    """MPEG location lookup table."""
    _framespec = [
        ('frames', 0), ('bytes', 0), ('milliseconds', 0),
        ('bits_for_bytes', 0), ('bits_for_milliseconds', 0), ('data', b''),
    ]


class SYTC(Frame):
    """Synced tempo codes."""
    _framespec = [('format', 2), ('data', b'')]


class CRM(Frame):
    """Encrypted meta frame (v2.2 only)."""
    _framespec = [('owner', ''), ('desc', ''), ('data', b'')]


class CHAP(Frame):
    """Chapter."""
    _framespec = [
        ('element_id', ''), ('start_time', 0), ('end_time', 0),
        ('start_offset', 0xFFFFFFFF), ('end_offset', 0xFFFFFFFF),
        ('sub_frames', None),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.sub_frames is None:
            self.sub_frames = {}


class CTOC(Frame):
    """Table of Contents."""
    _framespec = [
        ('element_id', ''), ('flags', CTOCFlags.TOP_LEVEL),
        ('child_element_ids', None), ('sub_frames', None),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.child_element_ids is None:
            self.child_element_ids = []
        if self.sub_frames is None:
            self.sub_frames = {}


# ──────────────────────────────────────────────────────────────
# v2.3/v2.4 Frames dict
# ──────────────────────────────────────────────────────────────

Frames = {
    'TALB': TALB, 'TBPM': TBPM, 'TCOM': TCOM, 'TCON': TCON, 'TCOP': TCOP,
    'TCMP': TCMP, 'TDAT': TDAT, 'TDEN': TDEN, 'TDES': TDES, 'TKWD': TKWD,
    'TCAT': TCAT, 'MVNM': MVNM, 'MVIN': MVIN, 'GRP1': GRP1,
    'TDOR': TDOR, 'TDLY': TDLY, 'TDRC': TDRC, 'TDRL': TDRL, 'TDTG': TDTG,
    'TENC': TENC, 'TEXT': TEXT, 'TFLT': TFLT, 'TGID': TGID, 'TIME': TIME,
    'TIT1': TIT1, 'TIT2': TIT2, 'TIT3': TIT3, 'TKEY': TKEY, 'TLAN': TLAN,
    'TLEN': TLEN, 'TMED': TMED, 'TMOO': TMOO, 'TOAL': TOAL, 'TOFN': TOFN,
    'TOLY': TOLY, 'TOPE': TOPE, 'TORY': TORY, 'TOWN': TOWN,
    'TPE1': TPE1, 'TPE2': TPE2, 'TPE3': TPE3, 'TPE4': TPE4,
    'TPOS': TPOS, 'TPRO': TPRO, 'TPUB': TPUB, 'TRCK': TRCK, 'TRDA': TRDA,
    'TRSN': TRSN, 'TRSO': TRSO, 'TSIZ': TSIZ,
    'TSO2': TSO2, 'TSOA': TSOA, 'TSOC': TSOC, 'TSOP': TSOP, 'TSOT': TSOT,
    'TSRC': TSRC, 'TSSE': TSSE, 'TSST': TSST, 'TYER': TYER,
    'TXXX': TXXX,
    # URL frames
    'WCOM': WCOM, 'WCOP': WCOP, 'WFED': WFED, 'WOAF': WOAF, 'WOAR': WOAR,
    'WOAS': WOAS, 'WORS': WORS, 'WPAY': WPAY, 'WPUB': WPUB, 'WXXX': WXXX,
    # Paired text
    'TIPL': TIPL, 'TMCL': TMCL, 'IPLS': IPLS,
    # Complex frames
    'APIC': APIC, 'USLT': USLT, 'SYLT': SYLT, 'COMM': COMM,
    'RVA2': RVA2, 'EQU2': EQU2, 'RVAD': RVAD, 'RVRB': RVRB,
    'POPM': POPM, 'PCNT': PCNT, 'PCST': PCST, 'GEOB': GEOB,
    'RBUF': RBUF, 'AENC': AENC, 'LINK': LINK, 'POSS': POSS,
    'UFID': UFID, 'USER': USER, 'OWNE': OWNE, 'COMR': COMR,
    'ENCR': ENCR, 'GRID': GRID, 'PRIV': PRIV, 'SIGN': SIGN,
    'SEEK': SEEK, 'ASPI': ASPI, 'MCDI': MCDI, 'ETCO': ETCO,
    'MLLT': MLLT, 'SYTC': SYTC,
    'CHAP': CHAP, 'CTOC': CTOC,
}


# ──────────────────────────────────────────────────────────────
# v2.2 frame aliases (3-char names)
# ──────────────────────────────────────────────────────────────

def _alias(name, parent):
    """Create a v2.2 alias that subclasses the v2.3/4 frame."""
    cls = type(name, (parent,), {'__doc__': f'v2.2 alias for {parent.__name__}'})
    return cls


UFI = _alias('UFI', UFID)
TT1 = _alias('TT1', TIT1)
TT2 = _alias('TT2', TIT2)
TT3 = _alias('TT3', TIT3)
TP1 = _alias('TP1', TPE1)
TP2 = _alias('TP2', TPE2)
TP3 = _alias('TP3', TPE3)
TP4 = _alias('TP4', TPE4)
TCM = _alias('TCM', TCOM)
TXT = _alias('TXT', TEXT)
TLA = _alias('TLA', TLAN)
TCO = _alias('TCO', TCON)
TAL = _alias('TAL', TALB)
TPA = _alias('TPA', TPOS)
TRK = _alias('TRK', TRCK)
TRC = _alias('TRC', TSRC)
TYE = _alias('TYE', TYER)
TDA = _alias('TDA', TDAT)
TIM = _alias('TIM', TIME)
TRD = _alias('TRD', TRDA)
TMT = _alias('TMT', TMED)
TFT = _alias('TFT', TFLT)
TBP = _alias('TBP', TBPM)
TCP = _alias('TCP', TCMP)
TCR = _alias('TCR', TCOP)
TPB = _alias('TPB', TPUB)
TEN = _alias('TEN', TENC)
TST = _alias('TST', TSOT)
TSA = _alias('TSA', TSOA)
TS2 = _alias('TS2', TSO2)
TSP = _alias('TSP', TSOP)
TSC = _alias('TSC', TSOC)
TSS = _alias('TSS', TSSE)
TOF = _alias('TOF', TOFN)
TLE = _alias('TLE', TLEN)
TSI = _alias('TSI', TSIZ)
TDY = _alias('TDY', TDLY)
TKE = _alias('TKE', TKEY)
TOT = _alias('TOT', TOAL)
TOA = _alias('TOA', TOPE)
TOL = _alias('TOL', TOLY)
TOR = _alias('TOR', TORY)
TXX = _alias('TXX', TXXX)
WAF = _alias('WAF', WOAF)
WAR = _alias('WAR', WOAR)
WAS = _alias('WAS', WOAS)
WCM = _alias('WCM', WCOM)
WCP = _alias('WCP', WCOP)
WPB = _alias('WPB', WPUB)
WXX = _alias('WXX', WXXX)
IPL = _alias('IPL', IPLS)
MCI = _alias('MCI', MCDI)
ETC = _alias('ETC', ETCO)
MLL = _alias('MLL', MLLT)
STC = _alias('STC', SYTC)
ULT = _alias('ULT', USLT)
SLT = _alias('SLT', SYLT)
COM = _alias('COM', COMM)
RVA = _alias('RVA', RVAD)
REV = _alias('REV', RVRB)
PIC = _alias('PIC', APIC)
GEO = _alias('GEO', GEOB)
CNT = _alias('CNT', PCNT)
POP = _alias('POP', POPM)
BUF = _alias('BUF', RBUF)
CRA = _alias('CRA', AENC)
LNK = _alias('LNK', LINK)
MVN = _alias('MVN', MVNM)
MVI = _alias('MVI', MVIN)
GP1 = _alias('GP1', GRP1)


Frames_2_2 = {
    'UFI': UFI, 'TT1': TT1, 'TT2': TT2, 'TT3': TT3,
    'TP1': TP1, 'TP2': TP2, 'TP3': TP3, 'TP4': TP4,
    'TCM': TCM, 'TXT': TXT, 'TLA': TLA, 'TCO': TCO,
    'TAL': TAL, 'TPA': TPA, 'TRK': TRK, 'TRC': TRC,
    'TYE': TYE, 'TDA': TDA, 'TIM': TIM, 'TRD': TRD,
    'TMT': TMT, 'TFT': TFT, 'TBP': TBP, 'TCP': TCP,
    'TCR': TCR, 'TPB': TPB, 'TEN': TEN, 'TST': TST,
    'TSA': TSA, 'TS2': TS2, 'TSP': TSP, 'TSC': TSC,
    'TSS': TSS, 'TOF': TOF, 'TLE': TLE, 'TSI': TSI,
    'TDY': TDY, 'TKE': TKE, 'TOT': TOT, 'TOA': TOA,
    'TOL': TOL, 'TOR': TOR, 'TXX': TXX,
    'WAF': WAF, 'WAR': WAR, 'WAS': WAS, 'WCM': WCM,
    'WCP': WCP, 'WPB': WPB, 'WXX': WXX,
    'IPL': IPL, 'MCI': MCI, 'ETC': ETC, 'MLL': MLL,
    'STC': STC, 'ULT': ULT, 'SLT': SLT, 'COM': COM,
    'RVA': RVA, 'REV': REV, 'PIC': PIC, 'GEO': GEO,
    'CNT': CNT, 'POP': POP, 'BUF': BUF, 'CRA': CRA,
    'LNK': LNK, 'MVN': MVN, 'MVI': MVI, 'GP1': GP1,
}
