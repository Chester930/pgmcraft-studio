"""
Unit tests for DAWProfileRegistry factory and profile filtering.
"""

import os
import tempfile
import pytest
from pgm_craft.daw_exporter import DAWProfileRegistry


def test_daw_profile_registry_supported():
    profiles = DAWProfileRegistry.get_supported_profiles()
    assert "reaper" in profiles
    assert "ableton" in profiles
    assert "logic" in profiles
    assert "cubase" in profiles
    assert "all" in profiles


def test_daw_profile_registry_export_single():
    registry = DAWProfileRegistry()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "test.wav",
            "average_bpm": 120.0,
            "chord_progression": []
        }
        files = registry.export_profile("reaper", report, output_dir=temp_dir)

        assert "reaper_project" in files
        assert os.path.exists(files["reaper_project"])
        assert "ableton_project" not in files


def test_daw_profile_registry_export_all():
    registry = DAWProfileRegistry()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "test.wav",
            "average_bpm": 120.0,
            "chord_progression": []
        }
        files = registry.export_profile("all", report, output_dir=temp_dir)

        assert "reaper_project" in files
        assert "ableton_project" in files
        assert "logic_pro_project" in files
        assert "cubase_tempo_map" in files
