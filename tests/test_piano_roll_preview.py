"""
Unit tests for Piano Roll Preview renderer in Gradio Web App.
"""

import pytest
from app import render_piano_roll_html


def test_render_piano_roll_html_empty():
    report = {}
    html = render_piano_roll_html(report)
    assert "<svg" in html or "待分析" in html


def test_render_piano_roll_html_with_data():
    report = {
        "total_measures": 4,
        "estimated_key": "C Major",
        "chord_progression": [
            {"measure": 1, "chord": "Cmaj", "start_time": 0.0, "end_time": 2.0},
            {"measure": 2, "chord": "Gmaj", "start_time": 2.0, "end_time": 4.0},
        ],
        "sections": [
            {"measure": 1, "name": "Intro", "start_time": 0.0},
            {"measure": 2, "name": "Verse 1", "start_time": 2.0},
        ]
    }
    html = render_piano_roll_html(report)

    assert "<svg" in html
    assert "Cmaj" in html
    assert "Gmaj" in html
    assert "Intro" in html
