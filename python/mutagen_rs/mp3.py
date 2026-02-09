"""mutagen_rs.mp3 - MP3/ID3 file handler.

Drop-in replacement for mutagen.mp3.
"""
from . import (
    MP3,
    EasyMP3,
    MPEGInfo,
    MP3Error,
    HeaderNotFoundError,
    MutagenError,
)

__all__ = ['MP3', 'EasyMP3', 'MPEGInfo', 'MP3Error', 'HeaderNotFoundError']
