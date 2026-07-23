"""
Unit tests for Live Stage Operator Dashboard HTML Generator.
"""

import os
import tempfile
import pytest
from pgm_craft.daw_exporter import DAWExporter


def test_generate_live_dashboard_html():
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        report = {
            "audio_file": "live_song.wav",
            "average_bpm": 128.0,
            "min_bpm": 124.0,
            "max_bpm": 132.0,
            "estimated_key": "A Minor",
            "total_measures": 8,
            "chord_progression": [
                {"measure": 1, "chord": "Am", "start_time": 0.0, "end_time": 2.0},
                {"measure": 2, "chord": "Fmaj", "start_time": 2.0, "end_time": 4.0},
            ],
            "sections": [
                {"measure": 1, "name": "Intro", "start_time": 0.0},
                {"measure": 2, "name": "Verse 1", "start_time": 2.0},
            ]
        }
        html_path = exporter.generate_live_dashboard_html(report, output_dir=temp_dir)

        assert os.path.exists(html_path)
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "<!DOCTYPE html>" in content
        assert "PGMCraft Live Stage Operator Dashboard" in content
        assert "128.0" in content or "128" in content
        assert "A Minor" in content
        assert "Intro" in content
        assert "Am" in content
