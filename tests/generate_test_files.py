#!/usr/bin/env python3
"""Generate test audio files with known metadata using mutagen.

Creates test files in test_files/generated/ with a ground_truth.json
that records the expected metadata for verification.
"""
import json
import os

from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TRCK, TDRC, TCON, TXXX, COMM,
    POPM,
)
from mutagen.flac import FLAC, Picture
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
TEST_DIR = os.path.join(PROJECT_DIR, "test_files")
GEN_DIR = os.path.join(TEST_DIR, "generated")
TRUTH_FILE = os.path.join(GEN_DIR, "ground_truth.json")


def make_mp3_silence(path, duration_ms=100):
    """Create a minimal valid MP3 file (silence)."""
    # Minimal MPEG1 Layer 3 frame: 128kbps, 44100Hz, stereo
    # Frame size = 144 * bitrate / samplerate + padding
    # = 144 * 128000 / 44100 = 417 bytes (no padding)
    frame_header = b'\xff\xfb\x90\x00'  # MPEG1 Layer3 128kbps 44100Hz stereo
    frame_size = 417
    frame = frame_header + b'\x00' * (frame_size - 4)
    # ~26ms per frame at 44100Hz (1152 samples)
    n_frames = max(1, duration_ms // 26)
    with open(path, 'wb') as f:
        f.write(frame * n_frames)


def make_flac_silence(path):
    """Create a minimal valid FLAC file."""
    # Use an existing FLAC as template
    src = os.path.join(TEST_DIR, "silence-44-s.flac")
    if os.path.exists(src):
        import shutil
        shutil.copy2(src, path)
        # Clear existing tags
        f = FLAC(path)
        f.delete()
        f.save()
    else:
        # Create minimal FLAC header
        # fLaC magic + minimal streaminfo block
        si = bytearray(38)  # 4 magic + 34 streaminfo
        si[0:4] = b'fLaC'
        si[4] = 0x80  # last block, type 0 (streaminfo)
        si[5:8] = (34).to_bytes(3, 'big')  # block size
        si[8:10] = (4096).to_bytes(2, 'big')  # min block size
        si[10:12] = (4096).to_bytes(2, 'big')  # max block size
        # sample rate 44100, 2 channels, 16 bits
        sr_ch_bps = (44100 << 4) | ((2 - 1) << 1) | ((16 - 1) >> 4)
        si[18] = (sr_ch_bps >> 16) & 0xff
        si[19] = (sr_ch_bps >> 8) & 0xff
        si[20] = (sr_ch_bps & 0xff) | (((16 - 1) & 0xf) << 4)
        with open(path, 'wb') as f:
            f.write(si)


def make_ogg_silence(path):
    """Create a minimal valid OGG Vorbis file."""
    src = os.path.join(TEST_DIR, "empty.ogg")
    if os.path.exists(src):
        import shutil
        shutil.copy2(src, path)
    else:
        print("WARNING: empty.ogg not found, skipping OGG generation")


def make_m4a_silence(path):
    """Create a minimal valid M4A file."""
    src = os.path.join(TEST_DIR, "has-tags.m4a")
    if os.path.exists(src):
        import shutil
        shutil.copy2(src, path)
        f = MP4(path)
        f.delete()
        f.save()
    else:
        print("WARNING: has-tags.m4a not found, skipping M4A generation")


def generate_mp3_basic(truth):
    """MP3 with basic text tags."""
    name = "mp3_basic.mp3"
    path = os.path.join(GEN_DIR, name)
    make_mp3_silence(path)

    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Test Title"]))
    tags.add(TPE1(encoding=3, text=["Test Artist"]))
    tags.add(TALB(encoding=3, text=["Test Album"]))
    tags.add(TRCK(encoding=3, text=["5/12"]))
    tags.add(TDRC(encoding=3, text=["2024"]))
    tags.add(TCON(encoding=3, text=["Rock"]))
    tags.save(path)

    truth[name] = {
        "format": "mp3",
        "tags": {
            "TIT2": ["Test Title"],
            "TPE1": ["Test Artist"],
            "TALB": ["Test Album"],
            "TRCK": ["5/12"],
            "TDRC": ["2024"],
            "TCON": ["Rock"],
        },
        "tag_count": 6,
    }


def generate_mp3_unicode(truth):
    """MP3 with Unicode text (CJK, emoji)."""
    name = "mp3_unicode.mp3"
    path = os.path.join(GEN_DIR, name)
    make_mp3_silence(path)

    tags = ID3()
    tags.add(TIT2(encoding=3, text=["\u6d4b\u8bd5\u6807\u9898"]))  # Chinese
    tags.add(TPE1(encoding=3, text=["\u30c6\u30b9\u30c8"]))  # Japanese
    tags.add(TALB(encoding=3, text=["\ud14c\uc2a4\ud2b8"]))  # Korean
    tags.save(path)

    truth[name] = {
        "format": "mp3",
        "tags": {
            "TIT2": ["\u6d4b\u8bd5\u6807\u9898"],
            "TPE1": ["\u30c6\u30b9\u30c8"],
            "TALB": ["\ud14c\uc2a4\ud2b8"],
        },
        "tag_count": 3,
    }


def generate_mp3_txxx(truth):
    """MP3 with TXXX user-defined text frames."""
    name = "mp3_txxx.mp3"
    path = os.path.join(GEN_DIR, name)
    make_mp3_silence(path)

    tags = ID3()
    tags.add(TIT2(encoding=3, text=["TXXX Test"]))
    tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_GAIN", text=["-6.5 dB"]))
    tags.add(TXXX(encoding=3, desc="CUSTOM_TAG", text=["custom value"]))
    tags.save(path)

    truth[name] = {
        "format": "mp3",
        "tags": {
            "TIT2": ["TXXX Test"],
            "TXXX:REPLAYGAIN_TRACK_GAIN": ["-6.5 dB"],
            "TXXX:CUSTOM_TAG": ["custom value"],
        },
        "tag_count": 3,
    }


def generate_mp3_comm(truth):
    """MP3 with COMM comment frames."""
    name = "mp3_comm.mp3"
    path = os.path.join(GEN_DIR, name)
    make_mp3_silence(path)

    tags = ID3()
    tags.add(TIT2(encoding=3, text=["COMM Test"]))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=["A comment"]))
    tags.add(COMM(encoding=3, lang="eng", desc="description", text=["Described comment"]))
    tags.save(path)

    truth[name] = {
        "format": "mp3",
        "tags": {
            "TIT2": ["COMM Test"],
            "COMM::eng": ["A comment"],
            "COMM:description:eng": ["Described comment"],
        },
        "tag_count": 3,
    }


def generate_mp3_popm(truth):
    """MP3 with POPM popularity frame."""
    name = "mp3_popm.mp3"
    path = os.path.join(GEN_DIR, name)
    make_mp3_silence(path)

    tags = ID3()
    tags.add(TIT2(encoding=3, text=["POPM Test"]))
    tags.add(POPM(email="user@example.com", rating=196, count=42))
    tags.save(path)

    truth[name] = {
        "format": "mp3",
        "tags": {
            "TIT2": ["POPM Test"],
        },
        "tag_count": 2,  # TIT2 + POPM
    }


def generate_flac_basic(truth):
    """FLAC with basic Vorbis comments."""
    name = "flac_basic.flac"
    path = os.path.join(GEN_DIR, name)
    make_flac_silence(path)
    if not os.path.exists(path):
        return

    f = FLAC(path)
    f["title"] = "FLAC Title"
    f["artist"] = "FLAC Artist"
    f["album"] = "FLAC Album"
    f["tracknumber"] = "3"
    f["date"] = "2024"
    f["genre"] = "Electronic"
    f.save()

    truth[name] = {
        "format": "flac",
        "tags": {
            "title": ["FLAC Title"],
            "artist": ["FLAC Artist"],
            "album": ["FLAC Album"],
            "tracknumber": ["3"],
            "date": ["2024"],
            "genre": ["Electronic"],
        },
        "tag_count": 6,
    }


def generate_flac_multivalue(truth):
    """FLAC with multi-value tags."""
    name = "flac_multivalue.flac"
    path = os.path.join(GEN_DIR, name)
    make_flac_silence(path)
    if not os.path.exists(path):
        return

    f = FLAC(path)
    f["title"] = "Multi Test"
    f["artist"] = ["Artist One", "Artist Two", "Artist Three"]
    f["genre"] = ["Rock", "Pop"]
    f.save()

    truth[name] = {
        "format": "flac",
        "tags": {
            "title": ["Multi Test"],
            "artist": ["Artist One", "Artist Two", "Artist Three"],
            "genre": ["Rock", "Pop"],
        },
        "tag_count": 3,
    }


def generate_flac_picture(truth):
    """FLAC with embedded picture."""
    name = "flac_picture.flac"
    path = os.path.join(GEN_DIR, name)
    make_flac_silence(path)
    if not os.path.exists(path):
        return

    f = FLAC(path)
    f["title"] = "Picture Test"

    # Create a minimal 1x1 PNG
    png_data = (
        b'\x89PNG\r\n\x1a\n'  # PNG signature
        b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02'
        b'\x00\x00\x00\x90wS\xde'
        b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05'
        b'\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )

    pic = Picture()
    pic.type = 3  # Cover (front)
    pic.mime = "image/png"
    pic.desc = "Cover"
    pic.width = 1
    pic.height = 1
    pic.depth = 24
    pic.data = png_data
    f.add_picture(pic)
    f.save()

    truth[name] = {
        "format": "flac",
        "tags": {
            "title": ["Picture Test"],
        },
        "tag_count": 1,
        "picture_count": 1,
    }


def generate_ogg_basic(truth):
    """OGG Vorbis with basic tags."""
    name = "ogg_basic.ogg"
    path = os.path.join(GEN_DIR, name)
    make_ogg_silence(path)
    if not os.path.exists(path):
        return

    f = OggVorbis(path)
    f["title"] = "OGG Title"
    f["artist"] = "OGG Artist"
    f["album"] = "OGG Album"
    f.save()

    truth[name] = {
        "format": "ogg",
        "tags": {
            "title": ["OGG Title"],
            "artist": ["OGG Artist"],
            "album": ["OGG Album"],
        },
        "tag_count": 3,
    }


def generate_m4a_basic(truth):
    """M4A with basic tags."""
    name = "m4a_basic.m4a"
    path = os.path.join(GEN_DIR, name)
    make_m4a_silence(path)
    if not os.path.exists(path):
        return

    f = MP4(path)
    f["\xa9nam"] = ["M4A Title"]
    f["\xa9ART"] = ["M4A Artist"]
    f["\xa9alb"] = ["M4A Album"]
    f["trkn"] = [(5, 12)]
    f["\xa9day"] = ["2024"]
    f.save()

    truth[name] = {
        "format": "m4a",
        "tags": {
            "\xa9nam": ["M4A Title"],
            "\xa9ART": ["M4A Artist"],
            "\xa9alb": ["M4A Album"],
            "trkn": [(5, 12)],
            "\xa9day": ["2024"],
        },
        "tag_count": 5,
    }


def main():
    os.makedirs(GEN_DIR, exist_ok=True)
    truth = {}

    generators = [
        generate_mp3_basic,
        generate_mp3_unicode,
        generate_mp3_txxx,
        generate_mp3_comm,
        generate_mp3_popm,
        generate_flac_basic,
        generate_flac_multivalue,
        generate_flac_picture,
        generate_ogg_basic,
        generate_m4a_basic,
    ]

    for gen in generators:
        try:
            gen(truth)
            print(f"  Generated: {gen.__name__}")
        except Exception as e:
            print(f"  FAILED: {gen.__name__}: {e}")

    with open(TRUTH_FILE, "w") as f:
        json.dump(truth, f, indent=2, ensure_ascii=False)

    print(f"\nGenerated {len(truth)} test files in {GEN_DIR}")
    print(f"Ground truth: {TRUTH_FILE}")


if __name__ == "__main__":
    main()
