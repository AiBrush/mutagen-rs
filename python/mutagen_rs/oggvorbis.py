"""mutagen_rs.oggvorbis - OGG Vorbis file handler.

Drop-in replacement for mutagen.oggvorbis.
"""
from . import (
    OggVorbis,
    OggVorbisInfo,
    OggError,
    MutagenError,
)

__all__ = ['OggVorbis', 'OggVorbisInfo', 'OggError']
