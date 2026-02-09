"""FLAC support types for mutagen API compatibility.

Provides Picture class matching mutagen.flac.Picture.
"""


class Picture:
    """FLAC picture metadata block.

    Compatible with mutagen.flac.Picture.
    """

    def __init__(self, data=None):
        self.type = 3  # COVER_FRONT default
        self.mime = ''
        self.desc = ''
        self.width = 0
        self.height = 0
        self.depth = 0
        self.colors = 0
        self.data = b''
        if data is not None and isinstance(data, bytes):
            self.data = data

    def __repr__(self):
        return (f'Picture(type={self.type}, mime={self.mime!r}, '
                f'desc={self.desc!r}, {self.width}x{self.height}, '
                f'{len(self.data)} bytes)')
