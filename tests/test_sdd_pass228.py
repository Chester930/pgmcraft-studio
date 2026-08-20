"""PASS-228: ground the headline beat-grid quality score in real kick-stem
audio, without touching _score_beat_grid_quality's body (used as an
internal accept/reject gate by other Stage3 nodes -- see
docs/PASS-228-BEAT-GRID-QUALITY-SCORE-REAL-GROUNDING-TASK.md).
"""

import os

import numpy as np
import pytest
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import (
    _kick_downbeat_accent_score,
    _score_beat_grid_grounded,
    _score_beat_grid_quality,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
REAL_KICK_PATH = os.path.join(
    ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems", "drums", "kick.wav"
)
REAL_GOLDEN_PATH = (
    r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
    r"\reports\measure_map.json"
)


def _write_synthetic_kick_wav(path, downbeat_times, sr=22050, duration_sec=8.0):
    """A kick track that only accents true downbeats -- a short loud burst
    at each time in downbeat_times, silence elsewhere."""
    y = np.zeros(int(duration_sec * sr), dtype=np.float32)
    burst_len = int(0.05 * sr)
    for t in downbeat_times:
        start = int(t * sr)
        end = min(len(y), start + burst_len)
        if start < len(y):
            y[start:end] = 1.0
    sf.write(path, y, sr)


def _measure_grid(downbeat_times, beat_interval, rotate=0):
    """4 beats per measure starting at each downbeat time. rotate=1 shifts
    every beat's label by one position (regular spacing, wrong phase)."""
    beats = []
    for db in downbeat_times:
        for i in range(4):
            t = db + i * beat_interval
            label = ((i + rotate) % 4) + 1
            beats.append([t, label])
    return beats


def test_phase_rotated_grid_scores_lower_under_grounded_formula(tmp_path):
    # Offset well away from t=0: _score_beat_grid_quality's section_alignment
    # fallback (no real `sections` passed, see PASS-228-*.md section 0)
    # checks distance from the nearest downbeat to a fake single section at
    # t=0, which incidentally reacts to rotation if the grid starts near
    # zero. Starting the grid far from 0 keeps that fallback ~0 either way,
    # isolating tempo_stability/downbeat_consistency's blindness -- the
    # actual thing this test exists to demonstrate.
    downbeat_times = [50.0, 52.0, 54.0, 56.0]
    beat_interval = 0.5
    duration_sec = 60.0
    kick_path = str(tmp_path / "kick.wav")
    _write_synthetic_kick_wav(kick_path, downbeat_times, duration_sec=duration_sec)

    correct_beats = _measure_grid(downbeat_times, beat_interval, rotate=0)
    rotated_beats = _measure_grid(downbeat_times, beat_interval, rotate=1)

    base_correct = _score_beat_grid_quality(correct_beats)
    base_rotated = _score_beat_grid_quality(rotated_beats)
    # Same timestamps, same interval regularity -- the OLD formula can't
    # tell these apart at all. This is the exact blind spot Pass 228 exists
    # to fix; if this assertion ever fails, _score_beat_grid_quality's body
    # changed and the whole premise of this task needs re-checking.
    assert base_correct["score"] == base_rotated["score"]

    grounded_correct = _score_beat_grid_grounded(correct_beats, kick_stem_path=kick_path)
    grounded_rotated = _score_beat_grid_grounded(rotated_beats, kick_stem_path=kick_path)

    assert grounded_correct["kick_downbeat_accent"]["win_ratio"] == 1.0
    assert grounded_rotated["kick_downbeat_accent"]["win_ratio"] == 0.0
    assert grounded_correct["score"] > grounded_rotated["score"] + 15.0


def test_no_kick_stem_path_falls_back_to_base_score():
    beats = _measure_grid([0.0, 2.0, 4.0], 0.5)
    base = _score_beat_grid_quality(beats)
    grounded = _score_beat_grid_grounded(beats, kick_stem_path=None)
    assert grounded["score"] == base["score"]
    assert grounded["kick_downbeat_accent"] is None


def test_missing_kick_stem_file_falls_back_to_base_score():
    beats = _measure_grid([0.0, 2.0, 4.0], 0.5)
    base = _score_beat_grid_quality(beats)
    grounded = _score_beat_grid_grounded(beats, kick_stem_path="D:/does/not/exist.wav")
    assert grounded["score"] == base["score"]
    assert grounded["kick_downbeat_accent"]["win_ratio"] is None


def test_too_few_beats_returns_no_opinion(tmp_path):
    kick_path = str(tmp_path / "kick.wav")
    _write_synthetic_kick_wav(kick_path, [0.0])
    result = _kick_downbeat_accent_score([[0.0, 1], [0.5, 2]], kick_path)
    assert result["win_ratio"] is None
    assert "missing_downbeat_cycle" in result["warnings"]


@pytest.mark.skipif(
    not (os.path.exists(REAL_KICK_PATH) and os.path.exists(REAL_GOLDEN_PATH)),
    reason="cached World is Mine kick stem / golden reference not present in this environment",
)
def test_real_song_kick_accent_matches_pass227_segment_direction():
    import json

    with open(REAL_GOLDEN_PATH, encoding="utf-8") as f:
        measures = json.load(f)["measure_map"]

    segments = [
        ("Intro", 0.0, 25.813243),
        ("Verse 1", 25.813243, 86.907256),
        ("Chorus 1", 86.907256, 147.977778),
        ("Outro", 147.977778, float("inf")),
    ]
    results = {}
    for name, start, end in segments:
        beats = []
        for m in measures:
            t0 = m["beats"][0]["time"] if m.get("beats") else m["start_time"]
            if not (start <= t0 < end):
                continue
            for b in m.get("beats", []):
                beats.append([b["time"], b["beat"]])
        results[name] = _kick_downbeat_accent_score(beats, REAL_KICK_PATH)["win_ratio"]

    # Pass 227's independent verification found this exact ordering on the
    # real song (Verse1 76.2% > Chorus1 59.5% > Outro 30.0%, all vs a 25%
    # chance baseline). This test just confirms the production function
    # reproduces the same direction, not exact values.
    assert results["Verse 1"] > results["Chorus 1"] > results["Outro"]
    assert results["Outro"] < 0.4  # near the 25% chance baseline
    assert results["Verse 1"] > 0.6
