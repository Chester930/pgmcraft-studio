"""
Unit tests for 3 Breakthrough SDD Modules:
Module 1: VoiceSplitter (Piano Treble/Bass & Guitar BassLine/Chords)
Module 2: DAWExporter Bus Routing
Module 3: MIDIQuantizerGuardNode
"""

import os
import pytest
from pgm_craft.enhancer import VoiceSplitter, MIDIQuantizer
from pgm_craft.daw_exporter import DAWExporter
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import MIDIQuantizerGuardNode, VoiceSplitMIDIExportNode


def test_voice_splitter_piano():
    splitter = VoiceSplitter()
    notes = [
        {"pitch": 72, "start_time": 0.0, "end_time": 0.5},  # C5 (Right hand)
        {"pitch": 48, "start_time": 0.0, "end_time": 0.5},  # C3 (Left hand)
    ]
    right, left = splitter.split_piano_voices(notes, split_pitch=60)
    assert len(right) == 1
    assert right[0]["pitch"] == 72
    assert len(left) == 1
    assert left[0]["pitch"] == 48


def test_voice_splitter_guitar():
    splitter = VoiceSplitter()
    notes = [
        {"pitch": 64, "start_time": 0.0, "end_time": 0.5},  # E4 (Chord)
        {"pitch": 40, "start_time": 0.0, "end_time": 0.5},  # E2 (Bassline)
    ]
    bassline, chords = splitter.split_guitar_voices(notes, split_pitch=55)
    assert len(bassline) == 1
    assert bassline[0]["pitch"] == 40
    assert len(chords) == 1
    assert chords[0]["pitch"] == 64


def test_midi_quantizer_filter_short_notes():
    quantizer = MIDIQuantizer()
    notes = [
        {"pitch": 60, "start_time": 0.0, "end_time": 0.01},  # Noise < 0.08s
        {"pitch": 60, "start_time": 0.0, "end_time": 0.50},  # Valid Note
    ] + [{"pitch": 60, "start_time": float(i), "end_time": float(i)+0.5} for i in range(1, 6)]

    quantized = quantizer.quantize_notes(notes, bpm=120.0, min_duration_sec=0.08)
    # The first noise note should be filtered out
    assert len(quantized) == 6


def test_daw_exporter_bus_routing(tmp_path):
    exporter = DAWExporter()
    report = {
        "average_bpm": 120.0,
        "chord_progression": [{"measure": 1, "start_time": 0.0, "chord": "C"}],
        "outputs": {"click_track": "click.wav"}
    }
    rpp_path = exporter.export_reaper_project(report, output_dir=str(tmp_path))
    assert os.path.exists(rpp_path)
    with open(rpp_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "RHYTHM BUS" in content
    assert "MUSIC BUS" in content
    assert "VOCAL BUS" in content


def test_midi_quantizer_guard_node(tmp_path):
    node = MIDIQuantizerGuardNode()
    blackboard = Blackboard()
    blackboard.set_val("vocal_pitch", [{"pitch": 60, "start_time": 0.0, "end_time": 0.5}])
    blackboard.set_val("bpm", 120.0)

    status = node.execute(blackboard)
    assert status == NodeStatus.SUCCESS
    assert blackboard.get_val("quantized_vocal_notes") is not None
