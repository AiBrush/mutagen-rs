"""mutagen_rs.mp4 - MP4/M4A file handler.

Drop-in replacement for mutagen.mp4.
"""
from . import (
    MP4,
    MP4Info,
    MP4Tags,
    MP4Error,
    MutagenError,
)

__all__ = ['MP4', 'MP4Info', 'MP4Tags', 'MP4Error']
