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
