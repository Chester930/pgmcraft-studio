"""
Unit tests for DAW project file & Marker CSV exporters.
"""

import os
import tempfile
import pytest
from pgm_craft.daw_exporter import DAWExporter


def test_export_marker_csv():
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_chords = [
            {"measure": 1, "chord": "Cmaj", "start_time": 0.5, "end_time": 2.5},
            {"measure": 2, "chord": "Gmaj", "start_time": 2.5, "end_time": 4.5},
        ]
        csv_path = exporter.export_marker_csv(fake_chords, output_dir=temp_dir)
        
        assert os.path.exists(csv_path)
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Measure,Time,Chord" in content
        assert "1,0.5,Cmaj" in content
        assert "2,2.5,Gmaj" in content


def test_export_reaper_project():
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "test_audio.wav",
            "average_bpm": 120.0,
            "chord_progression": [
                {"measure": 1, "chord": "Cmaj", "start_time": 0.5, "end_time": 2.5},
            ],
            "outputs": {
                "click_track": "click_track.wav",
                "mix_with_click": "mix_with_click.wav",
                "tempo_map_midi": "tempo_map.mid",
                "click_guide_midi": "click_guide.mid",
            }
        }
        rpp_path = exporter.export_reaper_project(report, output_dir=temp_dir)

        assert os.path.exists(rpp_path)
        with open(rpp_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "<REAPER_PROJECT" in content
        assert "PGMCraft Studio" in content
        assert "TEMPO 120" in content
        assert "<TRACK" in content


def test_export_ableton_live_project():
    import gzip
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "test_audio.wav",
            "average_bpm": 128.0,
            "outputs": {
                "click_track": "click_track.wav",
            }
        }
        als_path = exporter.export_ableton_live_project(report, output_dir=temp_dir)

        assert os.path.exists(als_path)
        with gzip.open(als_path, "rb") as f:
            xml_content = f.read().decode("utf-8")

        assert "<Ableton" in xml_content
        assert "128.0" in xml_content or "128" in xml_content
        assert "PGMCraft Studio" in xml_content


def test_export_logic_pro_project():
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "test_audio.wav",
            "average_bpm": 120.0,
            "chord_progression": [
                {"measure": 1, "chord": "Cmaj", "start_time": 0.0},
                {"measure": 2, "chord": "Gmaj", "start_time": 2.0},
            ]
        }
        fcpxml_path = exporter.export_logic_pro_project(report, output_dir=temp_dir)

        assert os.path.exists(fcpxml_path)
        with open(fcpxml_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "<fcpxml" in content
        assert "PGMCraft Studio" in content
        assert 'value="M01: Cmaj"' in content or "Cmaj" in content


def test_export_cubase_tempo_track():
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "test_audio.wav",
            "average_bpm": 124.0,
            "chord_progression": [
                {"measure": 1, "chord": "Am", "start_time": 0.0},
            ]
        }
        csv_path = exporter.export_cubase_tempo_track(report, output_dir=temp_dir)

        assert os.path.exists(csv_path)
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Measure,Time_Seconds,BPM,Chord" in content
        assert "124.0" in content or "124" in content


