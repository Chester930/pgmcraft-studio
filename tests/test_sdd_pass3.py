"""
Unit tests for Pass 3 Refinements:
Module 1: MIDIQuantizer.fix_note_overlaps
Module 2: PGMCraftEngine tempo_variance_pct
Module 3: render_section_svg_roadmap
"""

import pytest
from pgm_craft.enhancer import MIDIQuantizer
from pgm_craft.workflow_report import render_section_svg_roadmap


def test_fix_note_overlaps():
    quantizer = MIDIQuantizer()
    overlapping_notes = [
        {"pitch": 60, "start_time": 0.0, "end_time": 1.0},
        {"pitch": 62, "start_time": 0.98, "end_time": 2.0},  # Overlaps by 0.02s
    ]

    fixed = quantizer.fix_note_overlaps(overlapping_notes, gap_sec=0.005)
    assert len(fixed) == 2
    # The first note's end_time should be adjusted to before 0.98s
    assert fixed[0]["end_time"] <= 0.975
    assert fixed[1]["start_time"] == 0.98


def test_render_section_svg_roadmap():
    sections = [
        {"name": "Intro", "start_time": 0.0, "end_time": 15.0},
        {"name": "Chorus", "start_time": 15.0, "end_time": 45.0},
    ]
    svg_html = render_section_svg_roadmap(sections, total_duration=180.0)

    assert "<svg" in svg_html
    assert "Intro" in svg_html
    assert "Chorus" in svg_html
    assert "#00f0ff" in svg_html  # Intro color
    assert "#ff007f" in svg_html  # Chorus color
