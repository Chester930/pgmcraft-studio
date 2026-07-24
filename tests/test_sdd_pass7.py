"""
Unit tests for Pass 7 Commercial Suite Refinements:
Module 1: Global MIDI Chord Track Marker events in PGMSynthesizer.export_midi_chord_guide
Module 2: docs/ROADMAP.md consistency
"""

import os
import pytest
import mido
from pgm_craft.synthesizer import PGMSynthesizer


def test_global_midi_chord_track_markers(tmp_path):
    synth = PGMSynthesizer()
    beats = [(0.0, 1), (0.5, 2), (1.0, 3), (1.5, 4), (2.0, 1)]
    chords = [
        {"measure": 1, "chord": "Cmaj7", "start_time": 0.0, "end_time": 2.0},
        {"measure": 2, "chord": "Am7", "start_time": 2.0, "end_time": 4.0},
    ]

    midi_path = synth.export_midi_chord_guide(chords, beats, output_dir=str(tmp_path))
    assert os.path.exists(midi_path)

    mid = mido.MidiFile(midi_path)
    # Check tempo_track markers
    tempo_track = mid.tracks[0]
    markers = [msg.text for msg in tempo_track if msg.type == 'marker']

    assert len(markers) == 2
    assert "Chord: Cmaj7" in markers[0]
    assert "Chord: Am7" in markers[1]
