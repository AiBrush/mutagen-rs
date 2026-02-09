"""mutagen_rs.flac - FLAC file handler.

Drop-in replacement for mutagen.flac.
"""
from . import (
    FLAC,
    StreamInfo,
    FLACError,
    FLACNoHeaderError,
    MutagenError,
)

__all__ = ['FLAC', 'StreamInfo', 'FLACError', 'FLACNoHeaderError']
