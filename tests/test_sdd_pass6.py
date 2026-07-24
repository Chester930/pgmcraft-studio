"""
Unit tests for Pass 6 Final Optimizations:
Module 1: PGMSynthesizer export_midi_click_guide with GM Drum mode (rimshot_cowbell vs woodblock)
Module 2: DAWExporter export_musicxml
"""

import os
import pytest
from pgm_craft.synthesizer import PGMSynthesizer
from pgm_craft.daw_exporter import DAWExporter


def test_export_midi_click_guide_gm_mode(tmp_path):
    synth = PGMSynthesizer()
    beats = [(0.0, 1), (0.5, 2), (1.0, 3), (1.5, 4)]
    midi_path = synth.export_midi_click_guide(beats, output_dir=str(tmp_path), mode="rimshot_cowbell")

    assert os.path.exists(midi_path)
    import mido
    mid = mido.MidiFile(midi_path)
    # Track 2 contains click notes
    notes = [msg.note for msg in mid.tracks[1] if msg.type == 'note_on']
    # Rimshot/Cowbell mode should contain pitch 56 (Cowbell) and 37 (Side stick)
    assert 56 in notes
    assert 37 in notes


def test_export_musicxml(tmp_path):
    exporter = DAWExporter()
    report = {
        "audio_file": "test.wav",
        "average_bpm": 120.0,
        "chord_progression": [{"measure": 1, "chord": "C"}]
    }
    xml_path = exporter.export_musicxml(report, output_dir=str(tmp_path))

    assert os.path.exists(xml_path)
    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "<score-partwise" in content
    assert "<work-title>test.wav - PGMCraft Score Guide</work-title>" in content
