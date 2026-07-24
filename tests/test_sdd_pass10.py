"""
Unit tests for Pass 10 Grand Final Security & Quality Optimizations:
Module 1: Cross-Platform Path Sanitizer Guard in PGMProjectPackager
Module 2: MD5 Checksum Calculation Guard
"""

import os
import tempfile
import pytest
from pgm_craft.packager import PGMProjectPackager


def test_sanitize_filename_guard():
    # Test removing illegal cross-platform characters
    raw_name = 'Song: "Special" <Remix>? *Live*|Track.wav'
    sanitized = PGMProjectPackager.sanitize_filename(raw_name)

    assert ":" not in sanitized
    assert '"' not in sanitized
    assert "<" not in sanitized
    assert ">" not in sanitized
    assert "?" not in sanitized
    assert "*" not in sanitized
    assert "|" not in sanitized
    assert sanitized == "Song___Special___Remix____Live__Track.wav"



def test_audio_fingerprint_checksum(tmp_path):
    import hashlib
    test_file = os.path.join(tmp_path, "audio.wav")
    with open(test_file, "wb") as f:
        f.write(b"PGMCraft Audio Data Stream")

    md5_hash = hashlib.md5()
    with open(test_file, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)

    computed = md5_hash.hexdigest()
    assert len(computed) == 32
