"""
Unit tests for SectionStructureNode music section segmentation node.
"""

import os
import tempfile
import pytest
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import SectionStructureNode
from pgm_craft.daw_exporter import DAWExporter


def test_section_structure_node_missing_keys():
    bb = Blackboard()
    node = SectionStructureNode()
    missing = bb.validate_strict(node)
    assert "measure_map" in missing


def test_section_structure_node_execution():
    bb = Blackboard()
    fake_measure_map = [
        {"measure": 1, "start_time": 0.0, "end_time": 2.0},
        {"measure": 2, "start_time": 2.0, "end_time": 4.0},
        {"measure": 3, "start_time": 4.0, "end_time": 6.0},
        {"measure": 4, "start_time": 6.0, "end_time": 8.0},
        {"measure": 5, "start_time": 8.0, "end_time": 10.0},
        {"measure": 6, "start_time": 10.0, "end_time": 12.0},
        {"measure": 7, "start_time": 12.0, "end_time": 14.0},
        {"measure": 8, "start_time": 14.0, "end_time": 16.0},
    ]
    bb.set_val("measure_map", fake_measure_map)

    node = SectionStructureNode()
    status = node.run(bb)

    assert status == NodeStatus.SUCCESS
    assert "sections" in bb
    sections = bb["sections"]
    assert len(sections) >= 2
    assert sections[0]["name"] == "Intro"


def test_daw_exporter_with_sections():
    exporter = DAWExporter()
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_chords = [
            {"measure": 1, "chord": "Cmaj", "start_time": 0.0, "end_time": 4.0},
            {"measure": 3, "chord": "Gmaj", "start_time": 4.0, "end_time": 8.0},
        ]
        fake_sections = [
            {"measure": 1, "name": "Intro", "start_time": 0.0},
            {"measure": 3, "name": "Verse 1", "start_time": 4.0},
        ]
        csv_path = exporter.export_marker_csv(fake_chords, fake_sections, output_dir=temp_dir)
        assert os.path.exists(csv_path)

        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Section" in content
        assert "Intro" in content
        assert "Verse 1" in content
