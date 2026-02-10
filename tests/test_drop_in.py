"""Tests for drop-in replacement compatibility.

Validates submodule imports, ID3 frame behavior, EasyID3/EasyMP3,
type names, version exports, and File(easy=True).
"""

import os
import pytest

import mutagen_rs

TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_files")


def get_test_file(name):
    path = os.path.join(TEST_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"Test file not found: {path}")
    return path


@pytest.fixture(autouse=True)
def clear_cache():
    mutagen_rs.clear_cache()
    yield
    mutagen_rs.clear_cache()


# ──────────────────────────────────────────────────────────────
# Phase 1: ID3 Frame Compatibility
# ──────────────────────────────────────────────────────────────

class TestID3ValueStr:
    """str() of ID3 values should use NUL separator like mutagen."""

    def test_single_value_str(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        assert str(f['TIT2']) == 'Silence'

    def test_multi_value_str_uses_nul(self):
        val = mutagen_rs._ID3Value(['a', 'b', 'c'])
        assert str(val) == 'a\x00b\x00c'

    def test_text_property(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        val = f['TIT2']
        assert val.text is val
        assert isinstance(val.text, list)

    def test_encoding_property(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        val = f['TIT2']
        assert val.encoding == mutagen_rs.Encoding.UTF8
        assert int(val.encoding) == 3

    def test_pprint_method(self):
        val = mutagen_rs._ID3Value(['Rock', 'Pop'])
        assert val._pprint() == 'Rock / Pop'


class TestEncoding:
    """Encoding enum should match mutagen.id3.Encoding."""

    def test_values(self):
        assert int(mutagen_rs.Encoding.LATIN1) == 0
        assert int(mutagen_rs.Encoding.UTF16) == 1
        assert int(mutagen_rs.Encoding.UTF16BE) == 2
        assert int(mutagen_rs.Encoding.UTF8) == 3

    def test_repr(self):
        assert 'UTF8' in repr(mutagen_rs.Encoding.UTF8)

    def test_is_int(self):
        assert isinstance(mutagen_rs.Encoding.UTF8, int)


# ──────────────────────────────────────────────────────────────
# Phase 2: Submodule Imports
# ──────────────────────────────────────────────────────────────

class TestSubmoduleImports:
    """All mutagen submodule paths should work."""

    def test_mp3_submodule(self):
        from mutagen_rs.mp3 import MP3, EasyMP3, MPEGInfo

    def test_flac_submodule(self):
        from mutagen_rs.flac import FLAC, StreamInfo, FLACError

    def test_oggvorbis_submodule(self):
        from mutagen_rs.oggvorbis import OggVorbis, OggVorbisInfo

    def test_mp4_submodule(self):
        from mutagen_rs.mp4 import MP4, MP4Info, MP4Tags

    def test_id3_submodule(self):
        from mutagen_rs.id3 import ID3, Encoding, ID3Error

    def test_easyid3_submodule(self):
        from mutagen_rs.easyid3 import EasyID3

    def test_easymp4_submodule(self):
        from mutagen_rs.easymp4 import EasyMP4Tags

    def test_mp3_submodule_functional(self):
        from mutagen_rs.mp3 import MP3
        f = MP3(get_test_file("silence-44-s.mp3"))
        assert f.info.sample_rate > 0

    def test_flac_submodule_functional(self):
        from mutagen_rs.flac import FLAC
        f = FLAC(get_test_file("silence-44-s.flac"))
        assert f.info.sample_rate > 0

    def test_oggvorbis_submodule_functional(self):
        from mutagen_rs.oggvorbis import OggVorbis
        f = OggVorbis(get_test_file("empty.ogg"))
        assert f.info.sample_rate > 0

    def test_mp4_submodule_functional(self):
        from mutagen_rs.mp4 import MP4
        f = MP4(get_test_file("has-tags.m4a"))
        assert f.info.sample_rate > 0


# ──────────────────────────────────────────────────────────────
# Phase 3: Top-level Exports
# ──────────────────────────────────────────────────────────────

class TestTopLevelExports:
    """mutagen-compatible top-level attributes should exist."""

    def test_version_tuple(self):
        assert isinstance(mutagen_rs.version, tuple)
        assert len(mutagen_rs.version) >= 3
        assert all(isinstance(x, int) for x in mutagen_rs.version)

    def test_version_string(self):
        assert isinstance(mutagen_rs.version_string, str)
        assert '.' in mutagen_rs.version_string

    def test_filetype(self):
        assert mutagen_rs.FileType is not None

    def test_tags(self):
        assert mutagen_rs.Tags is dict

    def test_metadata(self):
        assert mutagen_rs.Metadata is dict

    def test_padding_info(self):
        p = mutagen_rs.PaddingInfo()
        assert p.padding == -1
        assert p.size == 0

    def test_padding_info_args(self):
        p = mutagen_rs.PaddingInfo(padding=100, size=200)
        assert p.padding == 100
        assert p.size == 200


# ──────────────────────────────────────────────────────────────
# Phase 4: Return Types
# ──────────────────────────────────────────────────────────────

class TestReturnTypes:
    """Factory functions should return objects with correct type names."""

    def test_mp3_type_name(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        assert type(f).__name__ == 'MP3'

    def test_flac_type_name(self):
        f = mutagen_rs.FLAC(get_test_file("silence-44-s.flac"))
        assert type(f).__name__ == 'FLAC'

    def test_ogg_type_name(self):
        f = mutagen_rs.OggVorbis(get_test_file("empty.ogg"))
        assert type(f).__name__ == 'OggVorbis'

    def test_mp4_type_name(self):
        f = mutagen_rs.MP4(get_test_file("has-tags.m4a"))
        assert type(f).__name__ == 'MP4'

    def test_file_mp3_type_name(self):
        f = mutagen_rs.File(get_test_file("silence-44-s.mp3"))
        assert type(f).__name__ == 'MP3'

    def test_file_flac_type_name(self):
        f = mutagen_rs.File(get_test_file("silence-44-s.flac"))
        assert type(f).__name__ == 'FLAC'

    def test_isinstance_filetype(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        assert isinstance(f, mutagen_rs.FileType)

    def test_isinstance_dict(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        assert isinstance(f, dict)


# ──────────────────────────────────────────────────────────────
# Phase 5: EasyID3 / EasyMP3
# ──────────────────────────────────────────────────────────────

class TestEasyID3:
    """EasyID3 should map human-readable keys to ID3 frames."""

    def test_easy_keys(self):
        e = mutagen_rs.EasyID3(get_test_file("silence-44-s.mp3"))
        keys = list(e.keys())
        assert 'title' in keys
        assert 'artist' in keys
        assert 'album' in keys

    def test_easy_values(self):
        e = mutagen_rs.EasyID3(get_test_file("silence-44-s.mp3"))
        assert isinstance(e['title'], list)
        assert 'Silence' in e['title']

    def test_easy_info(self):
        e = mutagen_rs.EasyID3(get_test_file("silence-44-s.mp3"))
        assert e.info is not None
        assert e.info.sample_rate > 0

    def test_easy_tags_is_self(self):
        e = mutagen_rs.EasyID3(get_test_file("silence-44-s.mp3"))
        assert e.tags is e


class TestEasyMP3:
    """EasyMP3 should work like MP3 but with easy keys."""

    def test_easy_mp3_type(self):
        e = mutagen_rs.EasyMP3(get_test_file("silence-44-s.mp3"))
        assert type(e).__name__ == 'EasyMP3'

    def test_easy_mp3_keys(self):
        e = mutagen_rs.EasyMP3(get_test_file("silence-44-s.mp3"))
        assert 'title' in e.keys()
        assert 'artist' in e.keys()

    def test_easy_mp3_info(self):
        e = mutagen_rs.EasyMP3(get_test_file("silence-44-s.mp3"))
        assert e.info.sample_rate > 0

    def test_easy_mp3_tags(self):
        e = mutagen_rs.EasyMP3(get_test_file("silence-44-s.mp3"))
        assert isinstance(e.tags, mutagen_rs.EasyID3)


class TestFileEasy:
    """File(easy=True) should return Easy* variants."""

    def test_file_easy_mp3(self):
        f = mutagen_rs.File(get_test_file("silence-44-s.mp3"), easy=True)
        assert type(f).__name__ == 'EasyMP3'
        assert 'title' in f.keys()

    def test_file_easy_flac(self):
        f = mutagen_rs.File(get_test_file("silence-44-s.flac"), easy=True)
        # FLAC vorbis comments are already "easy"
        assert f is not None
        assert f.info.sample_rate > 0

    def test_file_easy_ogg(self):
        f = mutagen_rs.File(get_test_file("empty.ogg"), easy=True)
        assert f is not None

    def test_file_easy_mp4(self):
        f = mutagen_rs.File(get_test_file("has-tags.m4a"), easy=True)
        assert type(f).__name__ == 'EasyMP4'


# ──────────────────────────────────────────────────────────────
# Phase 6: batch_open ID3Value wrapping
# ──────────────────────────────────────────────────────────────

class TestBatchOpenID3:
    """batch_open() should wrap MP3 tag values in _ID3Value."""

    def test_batch_mp3_id3value(self):
        path = get_test_file("silence-44-s.mp3")
        result = mutagen_rs.batch_open([path])
        d = result[path]
        tags = d.get('tags', {})
        if tags:
            for k, v in tags.items():
                assert isinstance(v, mutagen_rs._ID3Value), \
                    f"batch tag {k} should be _ID3Value, got {type(v)}"

    def test_batch_mp3_str(self):
        path = get_test_file("silence-44-s.mp3")
        result = mutagen_rs.batch_open([path])
        d = result[path]
        tags = d.get('tags', {})
        if 'TIT2' in tags:
            assert str(tags['TIT2']) == 'Silence'


# ──────────────────────────────────────────────────────────────
# Cross-comparison with mutagen
# ──────────────────────────────────────────────────────────────

class TestMutagenComparison:
    """Compare mutagen_rs behavior with mutagen directly."""

    def test_str_separator_matches(self):
        """str(tags['TIT2']) should use same separator as mutagen."""
        import mutagen.mp3
        path = get_test_file("silence-44-s.mp3")
        m = mutagen.mp3.MP3(path)
        r = mutagen_rs.MP3(path)
        for key in ['TIT2', 'TPE1', 'TALB']:
            if key in m.tags:
                assert str(m.tags[key]) == str(r[key]), \
                    f"str({key}) mismatch: mutagen={str(m.tags[key])!r} vs rs={str(r[key])!r}"

    def test_easy_keys_match(self):
        """EasyID3 keys should match mutagen's EasyID3."""
        from mutagen.easyid3 import EasyID3 as MutagenEasyID3
        path = get_test_file("silence-44-s.mp3")
        m = MutagenEasyID3(path)
        r = mutagen_rs.EasyID3(path)
        assert set(m.keys()) == set(r.keys()), \
            f"Easy key mismatch: mutagen={sorted(m.keys())} vs rs={sorted(r.keys())}"

    def test_easy_values_match(self):
        """EasyID3 values should match mutagen's EasyID3."""
        from mutagen.easyid3 import EasyID3 as MutagenEasyID3
        path = get_test_file("silence-44-s.mp3")
        m = MutagenEasyID3(path)
        r = mutagen_rs.EasyID3(path)
        for key in m.keys():
            assert list(m[key]) == list(r[key]), \
                f"Easy[{key}] mismatch: mutagen={m[key]!r} vs rs={r[key]!r}"

    def test_file_easy_type_matches(self):
        """File(easy=True) type name should match mutagen."""
        import mutagen
        path = get_test_file("silence-44-s.mp3")
        m = mutagen.File(path, easy=True)
        r = mutagen_rs.File(path, easy=True)
        assert type(m).__name__ == type(r).__name__, \
            f"Type mismatch: mutagen={type(m).__name__} vs rs={type(r).__name__}"


# ──────────────────────────────────────────────────────────────
# Frame class construction and attributes
# ──────────────────────────────────────────────────────────────

class TestFrameClasses:
    """Frame classes should be constructable like mutagen frames."""

    def test_text_frame_construction(self):
        from mutagen_rs.id3 import TIT2, Encoding
        t = TIT2(encoding=Encoding.UTF8, text=['Test'])
        assert str(t) == 'Test'
        assert t.text == ['Test']
        assert t.encoding == Encoding.UTF8

    def test_text_frame_multi_value(self):
        from mutagen_rs.id3 import TPE1
        t = TPE1(encoding=3, text=['Artist1', 'Artist2'])
        assert str(t) == 'Artist1\x00Artist2'
        assert len(t) == 2
        assert list(t) == ['Artist1', 'Artist2']

    def test_txxx_hashkey(self):
        from mutagen_rs.id3 import TXXX
        t = TXXX(encoding=3, desc='replaygain', text=['0.5'])
        assert t.HashKey == 'TXXX:replaygain'
        assert t.FrameID == 'TXXX'

    def test_apic_construction(self):
        from mutagen_rs.id3 import APIC, PictureType
        a = APIC(encoding=0, mime='image/jpeg', type=PictureType.COVER_FRONT,
                 desc='Cover', data=b'\xff\xd8')
        assert a.mime == 'image/jpeg'
        assert a.type == PictureType.COVER_FRONT
        assert a.data == b'\xff\xd8'
        assert a.HashKey == 'APIC:Cover'

    def test_comm_construction(self):
        from mutagen_rs.id3 import COMM
        c = COMM(encoding=3, lang='eng', desc='', text=['A comment'])
        assert str(c) == 'A comment'
        assert c.HashKey == 'COMM::eng'

    def test_uslt_construction(self):
        from mutagen_rs.id3 import USLT
        u = USLT(encoding=3, lang='eng', desc='', text='Lyrics here')
        assert str(u) == 'Lyrics here'
        assert u.HashKey == 'USLT::eng'

    def test_popm_construction(self):
        from mutagen_rs.id3 import POPM
        p = POPM(email='user@test.com', rating=128, count=10)
        assert p.email == 'user@test.com'
        assert +p == 128
        assert p.HashKey == 'POPM:user@test.com'

    def test_numeric_text_frame(self):
        from mutagen_rs.id3 import TRCK
        t = TRCK(encoding=3, text=['3/12'])
        assert +t == 3

    def test_timestamp_frame(self):
        from mutagen_rs.id3 import TDRC, ID3TimeStamp
        t = TDRC(encoding=3, text=['2024-01-15'])
        assert isinstance(t.text[0], ID3TimeStamp)
        assert t.text[0].year == 2024

    def test_tcon_genres(self):
        from mutagen_rs.id3 import TCON
        t = TCON(encoding=3, text=['Rock', 'Pop'])
        assert t.genres == ['Rock', 'Pop']

    def test_url_frame(self):
        from mutagen_rs.id3 import WOAR
        w = WOAR(url='https://example.com')
        assert str(w) == 'https://example.com'

    def test_wxxx_hashkey(self):
        from mutagen_rs.id3 import WXXX
        w = WXXX(encoding=3, desc='homepage', url='https://example.com')
        assert w.HashKey == 'WXXX:homepage'

    def test_frame_append_extend(self):
        from mutagen_rs.id3 import TPE1
        t = TPE1(encoding=3, text=['Artist1'])
        t.append('Artist2')
        assert len(t) == 2
        t.extend(['Artist3', 'Artist4'])
        assert len(t) == 4

    def test_binary_frame(self):
        from mutagen_rs.id3 import MCDI
        m = MCDI(data=b'\x01\x02\x03')
        assert m.data == b'\x01\x02\x03'


class TestFrameDicts:
    """Frames and Frames_2_2 dicts should contain all frame classes."""

    def test_frames_count(self):
        from mutagen_rs.id3 import Frames
        assert len(Frames) >= 100

    def test_frames_2_2_count(self):
        from mutagen_rs.id3 import Frames_2_2
        assert len(Frames_2_2) >= 60

    def test_frames_contains_common(self):
        from mutagen_rs.id3 import Frames
        for name in ['TIT2', 'TPE1', 'TALB', 'TXXX', 'APIC', 'COMM', 'USLT', 'POPM']:
            assert name in Frames, f'{name} missing from Frames'

    def test_frames_2_2_inherits(self):
        from mutagen_rs.id3 import Frames, Frames_2_2
        # v2.2 TT2 should be subclass of v2.4 TIT2
        assert issubclass(Frames_2_2['TT2'], Frames['TIT2'])


class TestEnumsAndTypes:
    """All enums and support types should work."""

    def test_picture_type_values(self):
        assert int(mutagen_rs.PictureType.OTHER) == 0
        assert int(mutagen_rs.PictureType.COVER_FRONT) == 3
        assert int(mutagen_rs.PictureType.COVER_BACK) == 4

    def test_bitrate_mode_values(self):
        assert int(mutagen_rs.BitrateMode.UNKNOWN) == 0
        assert int(mutagen_rs.BitrateMode.CBR) == 1
        assert int(mutagen_rs.BitrateMode.VBR) == 2

    def test_id3_timestamp(self):
        ts = mutagen_rs.ID3TimeStamp('2024-03-15T10:30:00')
        assert ts.year == 2024
        assert ts.month == 3
        assert ts.day == 15
        assert str(ts) == '2024-03-15T10:30:00'

    def test_id3v1_save_options(self):
        assert int(mutagen_rs.ID3v1SaveOptions.REMOVE) == 0
        assert int(mutagen_rs.ID3v1SaveOptions.UPDATE) == 1
        assert int(mutagen_rs.ID3v1SaveOptions.CREATE) == 2

    def test_mp3_mode_constants(self):
        assert mutagen_rs.STEREO == 0
        assert mutagen_rs.MONO == 3


# ──────────────────────────────────────────────────────────────
# ID3 container methods
# ──────────────────────────────────────────────────────────────

class TestID3ContainerMethods:
    """getall/add/delall/setall should work on opened files."""

    def test_getall(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        result = f.getall('TIT2')
        assert len(result) >= 1

    def test_getall_empty(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        result = f.getall('NONEXISTENT')
        assert result == []

    def test_add_frame(self):
        from mutagen_rs.id3 import TIT2
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        frame = TIT2(encoding=3, text=['Added Title'])
        f.add(frame)
        assert 'TIT2' in f.keys()
        assert f['TIT2'] is frame

    def test_delall(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        assert 'TIT2' in f.keys()
        f.delall('TIT2')
        assert 'TIT2' not in f.keys()

    def test_setall(self):
        from mutagen_rs.id3 import TXXX
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        frames = [TXXX(encoding=3, desc='key1', text=['val1']),
                  TXXX(encoding=3, desc='key2', text=['val2'])]
        f.setall('TXXX', frames)
        assert 'TXXX:key1' in f.keys()
        assert 'TXXX:key2' in f.keys()

    def test_add_invalid_raises(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        with pytest.raises(TypeError):
            f.add("not a frame")


# ──────────────────────────────────────────────────────────────
# FLAC Picture support
# ──────────────────────────────────────────────────────────────

class TestFLACPicture:
    """FLAC should support add_picture/clear_pictures."""

    def test_picture_class(self):
        from mutagen_rs.flac import Picture
        p = Picture()
        assert p.type == 3
        assert p.data == b''
        p.mime = 'image/png'
        p.data = b'fakedata'
        assert p.mime == 'image/png'

    def test_add_picture(self):
        from mutagen_rs import Picture
        f = mutagen_rs.FLAC(get_test_file("silence-44-s.flac"))
        initial = len(f.pictures)
        p = Picture()
        p.mime = 'image/jpeg'
        p.data = b'\xff\xd8'
        f.add_picture(p)
        assert len(f.pictures) == initial + 1

    def test_clear_pictures(self):
        from mutagen_rs import Picture
        f = mutagen_rs.FLAC(get_test_file("silence-44-s.flac"))
        p = Picture()
        p.data = b'test'
        f.add_picture(p)
        f.clear_pictures()
        assert len(f.pictures) == 0


# ──────────────────────────────────────────────────────────────
# MP4Cover / MP4FreeForm
# ──────────────────────────────────────────────────────────────

class TestMP4Types:
    """MP4Cover and MP4FreeForm should work like mutagen."""

    def test_mp4cover_construction(self):
        from mutagen_rs.mp4 import MP4Cover, AtomDataType
        c = MP4Cover(b'\x89PNG', imageformat=AtomDataType.PNG)
        assert bytes(c) == b'\x89PNG'
        assert c.imageformat == AtomDataType.PNG

    def test_mp4cover_default_jpeg(self):
        from mutagen_rs.mp4 import MP4Cover, AtomDataType
        c = MP4Cover(b'\xff\xd8')
        assert c.imageformat == AtomDataType.JPEG

    def test_mp4cover_format_constants(self):
        from mutagen_rs.mp4 import MP4Cover
        assert int(MP4Cover.FORMAT_JPEG) == 13
        assert int(MP4Cover.FORMAT_PNG) == 14

    def test_mp4freeform_construction(self):
        from mutagen_rs.mp4 import MP4FreeForm, AtomDataType
        f = MP4FreeForm(b'hello', dataformat=AtomDataType.UTF8)
        assert bytes(f) == b'hello'
        assert f.dataformat == AtomDataType.UTF8

    def test_atom_data_type(self):
        from mutagen_rs.mp4 import AtomDataType
        assert int(AtomDataType.JPEG) == 13
        assert int(AtomDataType.PNG) == 14
        assert int(AtomDataType.UTF8) == 1
        assert int(AtomDataType.INTEGER) == 21


# ──────────────────────────────────────────────────────────────
# MIME property
# ──────────────────────────────────────────────────────────────

class TestMimeProperty:
    """Files should have a mime property."""

    def test_mp3_mime(self):
        f = mutagen_rs.MP3(get_test_file("silence-44-s.mp3"))
        assert 'audio/mpeg' in f.mime

    def test_flac_mime(self):
        f = mutagen_rs.FLAC(get_test_file("silence-44-s.flac"))
        assert 'audio/flac' in f.mime

    def test_ogg_mime(self):
        f = mutagen_rs.OggVorbis(get_test_file("empty.ogg"))
        assert 'audio/ogg' in f.mime

    def test_mp4_mime(self):
        f = mutagen_rs.MP4(get_test_file("has-tags.m4a"))
        assert 'audio/mp4' in f.mime


# ──────────────────────────────────────────────────────────────
# Cross-comparison: frame imports match mutagen
# ──────────────────────────────────────────────────────────────

class TestFrameImportCompat:
    """Frame classes should be importable from same paths as mutagen."""

    def test_id3_frame_import(self):
        """Common import patterns from mutagen.id3 should work."""
        from mutagen_rs.id3 import TIT2, TPE1, TALB, TRCK, TCON, TXXX
        from mutagen_rs.id3 import APIC, COMM, USLT, POPM
        from mutagen_rs.id3 import Encoding, PictureType

    def test_mp4_type_import(self):
        from mutagen_rs.mp4 import MP4Cover, MP4FreeForm, AtomDataType

    def test_flac_picture_import(self):
        from mutagen_rs.flac import Picture, FLAC
