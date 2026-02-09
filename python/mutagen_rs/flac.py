"""mutagen_rs.flac - FLAC file handler.

Drop-in replacement for mutagen.flac.
"""
from . import (
    FLAC,
    StreamInfo,
    FLACError,
    FLACNoHeaderError,
    Picture,
)

__all__ = ['FLAC', 'StreamInfo', 'FLACError', 'FLACNoHeaderError', 'Picture']
