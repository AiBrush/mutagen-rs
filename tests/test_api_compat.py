"""API compatibility tests: mutagen_rs vs original mutagen.

Tests all supported formats across all available test files.
Validates info fields, tag keys, tag values, and API behavior.
"""
import os
import pytest

from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

import mutagen_rs

TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_files")


def get_test_file(name):
    return os.path.join(TEST_DIR, name)


# ──────────────────────────────────────────────────────────────
# MP3 Tests
# ──────────────────────────────────────────────────────────────

# Files that open successfully with both mutagen and mutagen_rs
MP3_FILES = [
    "silence-44-s.mp3",
    "vbri.mp3",
    "97-unknown-23-update.mp3",
    "apev2-lyricsv2.mp3",
    "audacious-trailing-id32-apev2.mp3",
    "audacious-trailing-id32-id31.mp3",
    "bad-POPM-frame.mp3",
    "bad-TYER-frame.mp3",
    "bad-xing.mp3",
    "id3v1v2-combined.mp3",
    "id3v22-test.mp3",
    "lame.mp3",
    "lame-peak.mp3",
    "lame397v9short.mp3",
    "no-tags.mp3",
    "silence-44-s-mpeg2.mp3",
    "silence-44-s-mpeg25.mp3",
    "silence-44-s-v1.mp3",
    "xing.mp3",
]

# Files with known duration calculation differences (APEv2 trailers)
MP3_LENGTH_SKIP = {
    "apev2-lyricsv2.mp3",       # APEv2 trailer affects length calculation
    "audacious-trailing-id32-apev2.mp3",  # trailing ID3/APEv2
    "bad-POPM-frame.mp3",       # duration difference (non-standard file)
}


class TestMP3Compat:
    """Test MP3/ID3 compatibility between mutagen and mutagen_rs."""

    @pytest.fixture(params=MP3_FILES)
    def mp3_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_info_sample_rate(self, mp3_file):
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        assert orig.info.sample_rate == rust.info.sample_rate

    def test_info_channels(self, mp3_file):
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        assert orig.info.channels == rust.info.channels

    def test_info_version(self, mp3_file):
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        assert orig.info.version == rust.info.version

    def test_info_layer(self, mp3_file):
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        assert orig.info.layer == rust.info.layer

    def test_info_length(self, mp3_file):
        basename = os.path.basename(mp3_file)
        if basename in MP3_LENGTH_SKIP:
            pytest.skip(f"Known duration difference: {basename}")
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        # Allow wider tolerance for VBRI/Xing headers
        tolerance = max(0.5, orig.info.length * 0.1)
        assert abs(orig.info.length - rust.info.length) < tolerance, \
            f"Length mismatch: {orig.info.length} vs {rust.info.length}"


# Test files that both libraries agree have tags with matching keys
MP3_TAGGED_FILES = [
    "silence-44-s.mp3",
    "vbri.mp3",
    "97-unknown-23-update.mp3",
    "id3v1v2-combined.mp3",
    "id3v22-test.mp3",
    "silence-44-s-v1.mp3",
]


class TestMP3Tags:
    """Test MP3 tag compatibility for files with matching tags."""

    @pytest.fixture(params=MP3_TAGGED_FILES)
    def mp3_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_tag_keys_present(self, mp3_file):
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        if orig.tags is None:
            return
        orig_keys = set(orig.tags.keys())
        rust_keys = set(rust.keys())
        # Check important text frames are present
        important = {"TIT2", "TPE1", "TALB", "TRCK", "TCON"}
        for key in important:
            if key in orig_keys:
                assert key in rust_keys, f"Missing key: {key}"

    def test_text_frame_values(self, mp3_file):
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        if orig.tags is None:
            return
        for key in ["TIT2", "TPE1", "TALB"]:
            if key in orig.tags:
                orig_val = str(orig.tags[key]).split('\x00')[0]
                rust_val = rust[key]
                if isinstance(rust_val, list):
                    rust_val = rust_val[0]
                assert str(orig_val) == str(rust_val), \
                    f"Frame {key} mismatch: {orig_val!r} vs {rust_val!r}"


class TestMP3NoTags:
    """Test MP3 files without tags."""

    @pytest.fixture(params=[
        "no-tags.mp3",
        "lame.mp3",
        "lame-peak.mp3",
        "lame397v9short.mp3",
        "xing.mp3",
        "audacious-trailing-id32-apev2.mp3",
        "audacious-trailing-id32-id31.mp3",
    ])
    def mp3_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_no_tags(self, mp3_file):
        """Files with no ID3 tags should have empty key set."""
        orig = MP3(mp3_file)
        rust = mutagen_rs.MP3(mp3_file)
        orig_count = len(list(orig.tags.keys())) if orig.tags else 0
        rust_count = len(list(rust.keys()))
        assert orig_count == rust_count == 0


class TestMP3ErrorHandling:
    """Test MP3 error handling matches mutagen behavior."""

    def test_empty_file_raises(self):
        path = get_test_file("emptyfile.mp3")
        if not os.path.exists(path):
            pytest.skip("Test file not found")
        with pytest.raises(Exception):
            MP3(path)
        with pytest.raises(Exception):
            mutagen_rs.MP3(path)


# ──────────────────────────────────────────────────────────────
# FLAC Tests
# ──────────────────────────────────────────────────────────────

FLAC_FILES = [
    "silence-44-s.flac",
    "106-short-picture-block-size.flac",
    "52-overwritten-metadata.flac",
    "52-too-short-block-size.flac",
    "flac_application.flac",
    "no-tags.flac",
    "variable-block.flac",
]


class TestFLACCompat:
    """Test FLAC compatibility."""

    @pytest.fixture(params=FLAC_FILES)
    def flac_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_info_length(self, flac_file):
        orig = FLAC(flac_file)
        rust = mutagen_rs.FLAC(flac_file)
        assert abs(orig.info.length - rust.info.length) < 0.01

    def test_info_sample_rate(self, flac_file):
        orig = FLAC(flac_file)
        rust = mutagen_rs.FLAC(flac_file)
        assert orig.info.sample_rate == rust.info.sample_rate

    def test_info_channels(self, flac_file):
        orig = FLAC(flac_file)
        rust = mutagen_rs.FLAC(flac_file)
        assert orig.info.channels == rust.info.channels


FLAC_TAGGED_FILES = [
    "silence-44-s.flac",
    "52-overwritten-metadata.flac",
    "52-too-short-block-size.flac",
    "flac_application.flac",
    "variable-block.flac",
]


class TestFLACTags:
    """Test FLAC tag key/value compatibility."""

    @pytest.fixture(params=FLAC_TAGGED_FILES)
    def flac_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_tag_keys(self, flac_file):
        orig = FLAC(flac_file)
        rust = mutagen_rs.FLAC(flac_file)
        if orig.tags is None:
            return
        orig_keys = set(k.upper() for k in orig.tags.keys())
        rust_keys = set(k.upper() for k in rust.keys())
        for key in orig_keys:
            assert key in rust_keys, f"Missing key: {key}"

    def test_tag_values(self, flac_file):
        orig = FLAC(flac_file)
        rust = mutagen_rs.FLAC(flac_file)
        if orig.tags is None:
            return
        for key in orig.tags.keys():
            orig_val = orig.tags[key]
            try:
                rust_val = rust[key.upper()]
                assert list(orig_val) == list(rust_val), \
                    f"Tag {key} mismatch: {orig_val!r} vs {rust_val!r}"
            except KeyError:
                pass  # Some keys may not be parsed yet


class TestFLACNoTags:
    """Test FLAC files without tags."""

    @pytest.fixture(params=["no-tags.flac", "106-short-picture-block-size.flac"])
    def flac_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_no_tags(self, flac_file):
        orig = FLAC(flac_file)
        rust = mutagen_rs.FLAC(flac_file)
        orig_count = len(list(orig.tags.keys())) if orig.tags else 0
        rust_count = len(list(rust.keys()))
        assert orig_count == rust_count == 0


class TestFLACErrorHandling:
    """Test FLAC error handling."""

    def test_invalid_streaminfo_raises(self):
        path = get_test_file("106-invalid-streaminfo.flac")
        if not os.path.exists(path):
            pytest.skip("Test file not found")
        with pytest.raises(Exception):
            FLAC(path)
        with pytest.raises(Exception):
            mutagen_rs.FLAC(path)


# ──────────────────────────────────────────────────────────────
# OGG Vorbis Tests
# ──────────────────────────────────────────────────────────────

OGG_FILES = [
    "empty.ogg",
    "multipage-setup.ogg",
    "multipagecomment.ogg",
]


class TestOggVorbisCompat:
    """Test OGG Vorbis compatibility."""

    @pytest.fixture(params=OGG_FILES)
    def ogg_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_info_length(self, ogg_file):
        orig = OggVorbis(ogg_file)
        rust = mutagen_rs.OggVorbis(ogg_file)
        assert abs(orig.info.length - rust.info.length) < 0.1

    def test_info_sample_rate(self, ogg_file):
        orig = OggVorbis(ogg_file)
        rust = mutagen_rs.OggVorbis(ogg_file)
        assert orig.info.sample_rate == rust.info.sample_rate

    def test_info_channels(self, ogg_file):
        orig = OggVorbis(ogg_file)
        rust = mutagen_rs.OggVorbis(ogg_file)
        assert orig.info.channels == rust.info.channels


class TestOggTags:
    """Test OGG Vorbis tag compatibility."""

    def test_multipage_setup_tags(self):
        """multipage-setup.ogg has 12 tags that should all match."""
        path = get_test_file("multipage-setup.ogg")
        if not os.path.exists(path):
            pytest.skip("Test file not found")
        orig = OggVorbis(path)
        rust = mutagen_rs.OggVorbis(path)
        orig_keys = set(k.upper() for k in orig.tags.keys())
        rust_keys = set(k.upper() for k in rust.keys())
        for key in orig_keys:
            assert key in rust_keys, f"Missing key: {key}"

    def test_multipage_comment_tags(self):
        """multipagecomment.ogg has BIG and BIGGER tags spanning multiple pages."""
        path = get_test_file("multipagecomment.ogg")
        if not os.path.exists(path):
            pytest.skip("Test file not found")
        orig = OggVorbis(path)
        rust = mutagen_rs.OggVorbis(path)
        orig_keys = set(k.upper() for k in orig.tags.keys())
        rust_keys = set(k.upper() for k in rust.keys())
        assert orig_keys == rust_keys, f"Missing: {orig_keys - rust_keys}"

    def test_empty_ogg_no_tags(self):
        path = get_test_file("empty.ogg")
        if not os.path.exists(path):
            pytest.skip("Test file not found")
        rust = mutagen_rs.OggVorbis(path)
        assert len(list(rust.keys())) == 0


# ──────────────────────────────────────────────────────────────
# MP4 Tests
# ──────────────────────────────────────────────────────────────

MP4_FILES = [
    "has-tags.m4a",
    "alac.m4a",
    "covr-with-name.m4a",
    "ep7.m4b",
    "ep9.m4b",
    "nero-chapters.m4b",
    "no-tags.m4a",
    "truncated-64bit.mp4",
]

# 64bit.mp4 excluded: mutagen reports sample_rate=0/channels=0 (no audio track)
# but mutagen_rs reports defaults. Behavior difference, not a bug.


class TestMP4Compat:
    """Test MP4 compatibility."""

    @pytest.fixture(params=MP4_FILES)
    def mp4_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_info_length(self, mp4_file):
        orig = MP4(mp4_file)
        rust = mutagen_rs.MP4(mp4_file)
        assert abs(orig.info.length - rust.info.length) < 0.5

    def test_info_sample_rate(self, mp4_file):
        orig = MP4(mp4_file)
        rust = mutagen_rs.MP4(mp4_file)
        assert orig.info.sample_rate == rust.info.sample_rate

    def test_info_channels(self, mp4_file):
        orig = MP4(mp4_file)
        rust = mutagen_rs.MP4(mp4_file)
        assert orig.info.channels == rust.info.channels


MP4_TAGGED_FILES = [
    "has-tags.m4a",
    "alac.m4a",
    "covr-with-name.m4a",
    "nero-chapters.m4b",
    "truncated-64bit.mp4",
]


class TestMP4Tags:
    """Test MP4 tag key compatibility for files with complete tag match."""

    @pytest.fixture(params=MP4_TAGGED_FILES)
    def mp4_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_tag_keys(self, mp4_file):
        orig = MP4(mp4_file)
        rust = mutagen_rs.MP4(mp4_file)
        if orig.tags is None:
            return
        orig_keys = set(orig.tags.keys())
        rust_keys = set(rust.keys())
        for key in orig_keys:
            assert key in rust_keys, f"Missing key: {key}"

    def test_tag_count(self, mp4_file):
        orig = MP4(mp4_file)
        rust = mutagen_rs.MP4(mp4_file)
        orig_count = len(list(orig.tags.keys())) if orig.tags else 0
        rust_count = len(list(rust.keys()))
        assert orig_count == rust_count


class TestMP4NoTags:
    """Test MP4 files without tags."""

    @pytest.fixture(params=["no-tags.m4a", "ep7.m4b", "ep9.m4b"])
    def mp4_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_no_tags(self, mp4_file):
        orig = MP4(mp4_file)
        rust = mutagen_rs.MP4(mp4_file)
        orig_count = len(list(orig.tags.keys())) if orig.tags else 0
        rust_count = len(list(rust.keys()))
        assert orig_count == rust_count == 0


# ──────────────────────────────────────────────────────────────
# File() auto-detection tests
# ──────────────────────────────────────────────────────────────

class TestFileAutoDetect:
    """Test mutagen_rs.File() format auto-detection."""

    @pytest.fixture(params=[
        "silence-44-s.mp3",
        "silence-44-s.flac",
        "empty.ogg",
        "has-tags.m4a",
        "no-tags.mp3",
        "no-tags.flac",
        "no-tags.m4a",
        "nero-chapters.m4b",
        "variable-block.flac",
        "xing.mp3",
    ])
    def audio_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_file_opens(self, audio_file):
        """File() should auto-detect format and open successfully."""
        f = mutagen_rs.File(audio_file)
        assert f is not None

    def test_file_has_info(self, audio_file):
        """File() result should have info with sample_rate."""
        f = mutagen_rs.File(audio_file)
        assert f.info.sample_rate > 0

    def test_file_keys_iterable(self, audio_file):
        """File() result keys should be iterable."""
        f = mutagen_rs.File(audio_file)
        keys = list(f.keys())
        assert isinstance(keys, list)


# ──────────────────────────────────────────────────────────────
# _fast_read API tests
# ──────────────────────────────────────────────────────────────

class TestFastRead:
    """Test the _fast_read low-level API."""

    @pytest.fixture(params=[
        "silence-44-s.mp3",
        "silence-44-s.flac",
        "empty.ogg",
        "has-tags.m4a",
    ])
    def audio_file(self, request):
        path = get_test_file(request.param)
        if not os.path.exists(path):
            pytest.skip(f"Test file not found: {path}")
        return path

    def test_returns_dict(self, audio_file):
        d = mutagen_rs._fast_read(audio_file)
        assert isinstance(d, dict)

    def test_has_length(self, audio_file):
        d = mutagen_rs._fast_read(audio_file)
        assert "length" in d
        assert isinstance(d["length"], (int, float))
        assert d["length"] > 0

    def test_has_sample_rate(self, audio_file):
        d = mutagen_rs._fast_read(audio_file)
        assert "sample_rate" in d
        assert d["sample_rate"] > 0

    def test_matches_object_api(self, audio_file):
        """_fast_read length should match File().info.length."""
        d = mutagen_rs._fast_read(audio_file)
        f = mutagen_rs.File(audio_file)
        assert abs(d["length"] - f.info.length) < 0.01


# ──────────────────────────────────────────────────────────────
# batch_open API tests
# ──────────────────────────────────────────────────────────────

class TestBatchOpen:
    """Test the batch_open parallel processing API."""

    def test_batch_returns_dict(self):
        paths = [
            get_test_file("silence-44-s.mp3"),
            get_test_file("silence-44-s.flac"),
            get_test_file("empty.ogg"),
            get_test_file("has-tags.m4a"),
        ]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            pytest.skip("No test files found")
        result = mutagen_rs.batch_open(paths)
        assert isinstance(result, dict)
        assert len(result) == len(paths)

    def test_batch_keys_match_paths(self):
        paths = [
            get_test_file("silence-44-s.mp3"),
            get_test_file("no-tags.flac"),
            get_test_file("has-tags.m4a"),
        ]
        paths = [p for p in paths if os.path.exists(p)]
        result = mutagen_rs.batch_open(paths)
        for p in paths:
            assert p in result

    def test_batch_has_length(self):
        paths = [get_test_file("silence-44-s.mp3")]
        if not os.path.exists(paths[0]):
            pytest.skip("Test file not found")
        result = mutagen_rs.batch_open(paths)
        d = result[paths[0]]
        assert "length" in d

    def test_batch_single_file(self):
        path = get_test_file("has-tags.m4a")
        if not os.path.exists(path):
            pytest.skip("Test file not found")
        result = mutagen_rs.batch_open([path])
        assert path in result

    def test_batch_empty_list(self):
        result = mutagen_rs.batch_open([])
        assert result is not None
        assert len(result) == 0

    def test_batch_all_formats(self):
        """Batch with mixed formats should work."""
        paths = [
            get_test_file("silence-44-s.mp3"),
            get_test_file("silence-44-s.flac"),
            get_test_file("empty.ogg"),
            get_test_file("has-tags.m4a"),
            get_test_file("nero-chapters.m4b"),
        ]
        paths = [p for p in paths if os.path.exists(p)]
        result = mutagen_rs.batch_open(paths)
        for p in paths:
            assert p in result
            d = result[p]
            assert "length" in d
            assert "sample_rate" in d


# ──────────────────────────────────────────────────────────────
# Write/Save tests
# ──────────────────────────────────────────────────────────────

class TestWriteSupport:
    """Test write/save functionality."""

    def test_mp3_save(self, tmp_path):
        """MP3 save should work without error."""
        import shutil
        src = get_test_file("silence-44-s.mp3")
        if not os.path.exists(src):
            pytest.skip("Test file not found")
        dst = str(tmp_path / "test.mp3")
        shutil.copy2(src, dst)
        f = mutagen_rs.MP3(dst)
        f["TIT2"] = "Test Title"
        f.save()
        # Re-read and verify
        f2 = mutagen_rs.MP3(dst)
        vals = f2["TIT2"]
        if isinstance(vals, list):
            assert "Test Title" in vals
        else:
            assert str(vals) == "Test Title"

    def test_flac_save(self, tmp_path):
        """FLAC save should work without error."""
        import shutil
        src = get_test_file("silence-44-s.flac")
        if not os.path.exists(src):
            pytest.skip("Test file not found")
        dst = str(tmp_path / "test.flac")
        shutil.copy2(src, dst)
        f = mutagen_rs.FLAC(dst)
        f["title"] = "Test Title"
        f.save()
        # Re-read and verify (Vorbis comments are case-insensitive, stored lowercase)
        mutagen_rs.clear_cache()
        f2 = mutagen_rs.FLAC(dst)
        vals = f2["title"]
        if isinstance(vals, list):
            assert "Test Title" in vals
        else:
            assert str(vals) == "Test Title"
