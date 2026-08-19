import json
from pathlib import Path

import numpy as np

from pgm_craft.workflow.madmom_hybrid import (
    DEFAULT_CV_THRESHOLD,
    DEFAULT_MIN_SPAN_BARS,
    DEFAULT_WINDOW_BARS,
    MadmomPrimarySegmentSpliceNode,
    _detect_weak_spans,
    _splice_weak_spans_with_fallback,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_detect_weak_spans_marks_variable_tempo_block():
    intervals = [1.5] * 5 + [1.0, 2.0, 1.1, 1.9, 1.0, 2.1] + [1.5] * 5
    downbeats = np.cumsum([0.0, *intervals]).tolist()

    spans = _detect_weak_spans(
        downbeats,
        window_bars=2,
        cv_threshold=0.2,
        min_span_bars=2,
    )

    assert spans
    unstable_start = downbeats[5]
    unstable_end = downbeats[11]
    assert any(start < unstable_end and end > unstable_start for start, end in spans)


def test_detect_weak_spans_does_not_use_sparse_density_as_signal():
    # Intro-like: very sparse evidence, but perfectly stable bar spacing.
    downbeats = np.arange(0.0, 30.0, 2.5).tolist()

    spans = _detect_weak_spans(
        downbeats,
        window_bars=5,
        cv_threshold=0.06,
        min_span_bars=2,
    )

    assert spans == []


def test_calibrated_defaults_detect_only_outro_in_committed_real_calibration():
    artifact_path = Path(__file__).parents[1] / "scratch" / "pass236_offline_calibration.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    selected = artifact["selected"]
    assert (DEFAULT_WINDOW_BARS, DEFAULT_CV_THRESHOLD, DEFAULT_MIN_SPAN_BARS) == (
        selected["window_bars"],
        selected["cv_threshold"],
        selected["min_span_bars"],
    )
    assert len(artifact["candidates"]) == artifact["candidate_count"]
    assert selected["selection_reason"]

    spans = _detect_weak_spans(artifact["madmom_downbeats"])
    expected = [tuple(span) for span in selected["spans"]]
    assert spans == expected
    outro_start, outro_end = artifact["sections"]["Outro"]
    assert spans
    assert all(start < outro_end and end > outro_start for start, end in spans)
    for name, (section_start, section_end) in artifact["sections"].items():
        if name != "Outro":
            assert all(not (start < section_end and end > section_start) for start, end in spans)


def test_splice_replaces_only_the_requested_weak_span():
    madmom = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    fallback = [0.0, 1.1, 2.1, 3.1, 4.1, 5.1, 6.1]

    merged, report = _splice_weak_spans_with_fallback(
        madmom,
        fallback,
        [(2.0, 4.0)],
        tolerance_sec=0.15,
    )

    assert merged == [0.0, 1.0, 2.1, 3.1, 4.1, 5.0, 6.0]
    assert report["status"] == "APPLIED"
    assert report["replaced_spans"][0]["madmom_removed_count"] == 3
    assert report["replaced_spans"][0]["fallback_inserted_count"] == 3
    assert all(
        entry["evidence_sources"] == ["v2_fallback_splice"]
        for entry in report["replaced_spans"][0]["inserted_downbeats"]
    )


def test_splice_gracefully_keeps_madmom_when_fallback_is_empty():
    madmom = [0.0, 1.0, 2.0, 3.0]

    merged, report = _splice_weak_spans_with_fallback(
        madmom,
        [],
        [(1.0, 2.0)],
    )

    assert merged == madmom
    assert report["status"] == "FALLBACK_UNAVAILABLE"
    assert report["replaced_spans"][0]["fallback_inserted_count"] == 0


def test_node_is_strictly_opt_in_and_preserves_default_grid(monkeypatch):
    original = np.asarray([[0.0, 1.0], [1.0, 1.0]], dtype=float)
    blackboard = Blackboard(
        {
            "audio_path": "unused.wav",
            "beats": original.copy(),
            "refined_beats": original.copy(),
            "barstart_v2_grid_beats": original.copy(),
        }
    )

    status = MadmomPrimarySegmentSpliceNode().execute(blackboard)

    assert status == NodeStatus.SUCCESS
    assert np.array_equal(blackboard["beats"], original)
    assert blackboard["madmom_hybrid_report"]["status"] == "DISABLED_OPT_IN_REQUIRED"


def test_node_uses_v2_fallback_only_inside_detected_span(monkeypatch):
    import pgm_craft.workflow.madmom_hybrid as hybrid

    monkeypatch.setattr(
        hybrid,
        "_run_madmom_dbn",
        lambda _audio_path, **_kwargs: np.asarray(
            [
                [0.0, 1.0],
                [0.5, 2.0],
                [1.0, 3.0],
                [1.5, 4.0],
                [2.0, 1.0],
                [3.8, 2.0],
                [4.4, 3.0],
            ],
            dtype=float,
        ),
    )
    madmom = np.asarray(
        [[0.0, 1.0], [0.5, 2.0], [1.0, 3.0], [1.5, 4.0], [2.0, 1.0], [3.8, 2.0], [4.4, 3.0]],
        dtype=float,
    )
    fallback = np.asarray(
        [[0.0, 1.0], [0.5, 2.0], [1.0, 3.0], [1.5, 4.0], [2.2, 1.0], [2.8, 2.0], [3.4, 3.0]],
        dtype=float,
    )
    blackboard = Blackboard(
        {
            "audio_path": "unused.wav",
            "madmom_hybrid_approved": True,
            "beats": madmom.copy(),
            "refined_beats": madmom.copy(),
            "barstart_v2_grid_beats": fallback,
            "madmom_hybrid_window_bars": 1,
            "madmom_hybrid_cv_threshold": 0.05,
            "madmom_hybrid_min_span_bars": 1,
        }
    )

    status = MadmomPrimarySegmentSpliceNode().execute(blackboard)

    assert status == NodeStatus.SUCCESS
    report = blackboard["madmom_hybrid_report"]
    assert report["approved"] is True
    assert report["status"] in {"APPLIED", "NO_WEAK_SPANS"}
    assert "evidence_sources" in report


def test_node_prefers_denoised_wav_path_over_target_analysis_path_and_audio_path(monkeypatch):
    # target_analysis_path is stem-specific by the time this node runs (e.g.
    # repointed at an isolated drums stem by SeparateDrumsNode), which
    # regressed Intro accuracy in Pass238's real production verify -- madmom
    # needs the stable full-mix denoised_wav_path, never the stem.
    import pgm_craft.workflow.madmom_hybrid as hybrid

    seen = []

    def fake_run(audio_path, **_kwargs):
        seen.append(audio_path)
        return np.asarray([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]], dtype=float)

    monkeypatch.setattr(hybrid, "_run_madmom_dbn", fake_run)
    grid = np.asarray([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]], dtype=float)
    blackboard = Blackboard(
        {
            "audio_path": "normalized-b-version.wav",
            "target_analysis_path": "stems/drums/drums.wav",
            "denoised_wav_path": "denoised-full-mix.wav",
            "madmom_hybrid_approved": True,
            "beats": grid.copy(),
            "refined_beats": grid.copy(),
            "barstart_v2_grid_beats": grid.copy(),
        }
    )

    status = MadmomPrimarySegmentSpliceNode().execute(blackboard)

    assert status == NodeStatus.SUCCESS
    assert seen == ["denoised-full-mix.wav"]
    assert blackboard["madmom_hybrid_report"]["audio_path"] == "denoised-full-mix.wav"


def test_node_falls_back_to_audio_path_when_denoised_wav_path_missing(monkeypatch):
    import pgm_craft.workflow.madmom_hybrid as hybrid

    seen = []

    def fake_run(audio_path, **_kwargs):
        seen.append(audio_path)
        return np.asarray([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]], dtype=float)

    monkeypatch.setattr(hybrid, "_run_madmom_dbn", fake_run)
    grid = np.asarray([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]], dtype=float)
    blackboard = Blackboard(
        {
            "audio_path": "legacy-caller-only-audio-path.wav",
            "target_analysis_path": "stems/drums/drums.wav",
            "madmom_hybrid_approved": True,
            "beats": grid.copy(),
            "refined_beats": grid.copy(),
            "barstart_v2_grid_beats": grid.copy(),
        }
    )

    status = MadmomPrimarySegmentSpliceNode().execute(blackboard)

    assert status == NodeStatus.SUCCESS
    assert seen == ["legacy-caller-only-audio-path.wav"]


def test_node_adds_trim_offset_to_madmom_grid_before_writing_beats(monkeypatch):
    import pgm_craft.workflow.madmom_hybrid as hybrid

    cropped_grid = np.asarray(
        [[0.0, 1.0], [0.5, 2.0], [1.0, 3.0], [1.5, 4.0]],
        dtype=float,
    )
    monkeypatch.setattr(hybrid, "_run_madmom_dbn", lambda _path, **_kwargs: cropped_grid.copy())
    blackboard = Blackboard(
        {
            "audio_path": "analysis.wav",
            "madmom_hybrid_approved": True,
            "trim_offset_sec": 2.5,
            "beats": cropped_grid.copy(),
            "refined_beats": cropped_grid.copy(),
            "barstart_v2_grid_beats": cropped_grid.copy(),
        }
    )

    status = MadmomPrimarySegmentSpliceNode().execute(blackboard)

    assert status == NodeStatus.SUCCESS
    np.testing.assert_allclose(
        blackboard["beats"][:, 0],
        cropped_grid[:, 0] + 2.5,
    )
    np.testing.assert_allclose(
        blackboard["refined_beats"][:, 0],
        cropped_grid[:, 0] + 2.5,
    )
    assert blackboard["madmom_hybrid_report"]["trim_offset_sec"] == 2.5
