"""MP4 support types for mutagen API compatibility.

Provides MP4Cover, MP4FreeForm, AtomDataType matching mutagen.mp4.
"""

from ._id3frames import _make_int_enum


AtomDataType = _make_int_enum('AtomDataType', [
    ('IMPLICIT', 0), ('UTF8', 1), ('UTF16', 2), ('SJIS', 3),
    ('HTML', 6), ('XML', 7), ('UUID', 8), ('ISRC', 9), ('MI3P', 10),
    ('GIF', 12), ('JPEG', 13), ('PNG', 14), ('URL', 15),
    ('DURATION', 16), ('DATETIME', 17), ('GENRES', 18), ('INTEGER', 21),
    ('RIAA_PA', 24), ('UPC', 25), ('BMP', 27),
])


class MP4Cover(bytes):
    """MP4 cover art, a bytes subclass with imageformat attribute.

    Compatible with mutagen.mp4.MP4Cover.
    """
    FORMAT_JPEG = AtomDataType.JPEG
    FORMAT_PNG = AtomDataType.PNG

    def __new__(cls, data=b'', imageformat=None):
        obj = bytes.__new__(cls, data)
        obj.imageformat = imageformat if imageformat is not None else AtomDataType.JPEG
        return obj

    def __repr__(self):
        return f'MP4Cover({bytes.__repr__(self)[:50]}..., imageformat={self.imageformat!r})'


class MP4FreeForm(bytes):
    """MP4 freeform data, a bytes subclass with dataformat and version.

    Compatible with mutagen.mp4.MP4FreeForm.
    """
    FORMAT_DATA = AtomDataType.IMPLICIT
    FORMAT_TEXT = AtomDataType.UTF8

    def __new__(cls, data=b'', dataformat=None, version=0):
        obj = bytes.__new__(cls, data)
        obj.dataformat = dataformat if dataformat is not None else AtomDataType.UTF8
        obj.version = version
        return obj

    def __repr__(self):
        return f'MP4FreeForm({bytes.__repr__(self)[:50]}..., dataformat={self.dataformat!r})'
