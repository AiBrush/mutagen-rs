"""mutagen_rs.id3 - ID3 tag handler.

Drop-in replacement for mutagen.id3.
"""
from . import (
    ID3,
    Encoding,
    ID3Error,
    ID3NoHeaderError,
    MutagenError,
    PaddingInfo,
)

__all__ = ['ID3', 'Encoding', 'ID3Error', 'ID3NoHeaderError', 'PaddingInfo']
