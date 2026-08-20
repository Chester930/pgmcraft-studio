"""SDD Pass 246: reuse legacy transient snap on madmom-hybrid output."""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import MicroTimingTransientSnapNode
from pgm_craft.workflow.madmom_hybrid import MadmomPrimarySegmentSpliceNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_existing_micro_timing_snap_moves_supported_beat_but_not_silent_beat(tmp_path):
    sr = 22050
    audio = np.zeros(sr * 2, dtype=np.float32)
    audio[int(0.485 * sr)] = 1.0
    drums_path = tmp_path / "drums.wav"
    sf.write(drums_path, audio, sr)

    blackboard = Blackboard(
        {
            "beats": np.asarray([[0.5, 2.0], [1.0, 3.0]], dtype=float),
            "stems": {"drums": str(drums_path)},
            "sr": sr,
        }
    )

    assert MicroTimingTransientSnapNode(search_window_ms=35.0).execute(blackboard) == NodeStatus.SUCCESS
    refined = blackboard["refined_beats"]
    assert abs(refined[0, 0] - 0.485) < 1.0 / sr
    assert abs(refined[1, 0] - 1.0) < 1.0 / sr
    assert any(abs(value) > 1.0 for value in blackboard["snap_offsets_ms"])
    assert blackboard["snap_skip_report"]["skipped_no_signal_count"] == 1


def test_existing_micro_timing_snap_ignores_low_amplitude_noise(tmp_path):
    sr = 22050
    rng = np.random.default_rng(246)
    audio = (rng.normal(0.0, 0.0001, sr * 2)).astype(np.float32)
    drums_path = tmp_path / "noisy-drums.wav"
    sf.write(drums_path, audio, sr)

    blackboard = Blackboard(
        {
            "beats": np.asarray([[1.0, 3.0]], dtype=float),
            "stems": {"drums": str(drums_path)},
            "sr": sr,
        }
    )

    assert MicroTimingTransientSnapNode(search_window_ms=35.0).execute(blackboard) == NodeStatus.SUCCESS
    assert abs(blackboard["refined_beats"][0, 0] - 1.0) < 1.0 / sr
    assert blackboard["snap_skip_report"]["skipped_no_signal_count"] == 1


def _hybrid_blackboard(enabled=None, drums_path=None):
    grid = np.asarray(
        [[0.0, 1.0], [0.5, 2.0], [1.0, 3.0], [1.5, 4.0]],
        dtype=float,
    )
    values = {
        "audio_path": "unused.wav",
        "madmom_hybrid_approved": True,
        "beats": grid.copy(),
        "refined_beats": grid.copy(),
        "barstart_v2_grid_beats": grid.copy(),
        "madmom_hybrid_cv_threshold": 1.0,
    }
    if enabled is not None:
        values["madmom_hybrid_micro_timing_snap_enabled"] = enabled
    if drums_path is not None:
        values.update({"stems": {"drums": str(drums_path)}, "sr": 22050})
    return Blackboard(values), grid


def test_hybrid_snap_is_applied_after_final_grid_and_reported(monkeypatch, tmp_path):
    import pgm_craft.workflow.madmom_hybrid as hybrid

    sr = 22050
    audio = np.zeros(sr * 2, dtype=np.float32)
    audio[int(0.485 * sr)] = 1.0
    drums_path = tmp_path / "drums.wav"
    sf.write(drums_path, audio, sr)
    blackboard, original = _hybrid_blackboard(drums_path=drums_path)
    monkeypatch.setattr(hybrid, "_run_madmom_dbn", lambda *_args, **_kwargs: original.copy())

    assert MadmomPrimarySegmentSpliceNode().execute(blackboard) == NodeStatus.SUCCESS
    assert abs(blackboard["beats"][1, 0] - 0.485) < 1.0 / sr
    report = blackboard["madmom_hybrid_report"]["micro_timing_snap_report"]
    assert report["status"] == "APPLIED"
    assert report["enabled"] is True
    assert report["nonzero_snap_count"] >= 1
    assert "snap_skip_report" in report


def test_hybrid_snap_flag_can_disable_and_hybrid_approval_still_gates_it(monkeypatch, tmp_path):
    import pgm_craft.workflow.madmom_hybrid as hybrid

    sr = 22050
    audio = np.zeros(sr * 2, dtype=np.float32)
    audio[int(0.485 * sr)] = 1.0
    drums_path = tmp_path / "drums.wav"
    sf.write(drums_path, audio, sr)

    monkeypatch.setattr(
        hybrid,
        "_run_madmom_dbn",
        lambda *_args, **_kwargs: np.asarray(
            [[0.0, 1.0], [0.5, 2.0], [1.0, 3.0], [1.5, 4.0]], dtype=float
        ),
    )
    disabled, original = _hybrid_blackboard(enabled=False, drums_path=drums_path)
    assert MadmomPrimarySegmentSpliceNode().execute(disabled) == NodeStatus.SUCCESS
    np.testing.assert_array_equal(disabled["beats"], original)
    assert disabled["madmom_hybrid_report"]["micro_timing_snap_report"]["status"] == "DISABLED_FLAG"

    gated, original = _hybrid_blackboard(enabled=True, drums_path=drums_path)
    gated["madmom_hybrid_approved"] = False
    assert MadmomPrimarySegmentSpliceNode().execute(gated) == NodeStatus.SUCCESS
    np.testing.assert_array_equal(gated["beats"], original)
    assert gated["madmom_hybrid_report"]["status"] == "DISABLED_OPT_IN_REQUIRED"


def test_hybrid_snap_never_moves_downbeats_even_with_a_louder_nearby_transient(monkeypatch, tmp_path):
    # Pass247's real-pipeline finding: a louder-but-wrong transient within
    # the +-35ms window can pull an already-correct downbeat off its real
    # position. Downbeats must always keep their pre-snap time; only beat
    # positions 2/3/4 (Pass245's actual target) may accept the snap.
    import pgm_craft.workflow.madmom_hybrid as hybrid

    sr = 22050
    audio = np.zeros(sr * 2, dtype=np.float32)
    audio[int(0.02 * sr)] = 1.0   # loud, wrong-beat transient near the downbeat
    audio[int(0.485 * sr)] = 0.5  # real transient near the beat-2 position
    drums_path = tmp_path / "drums.wav"
    sf.write(drums_path, audio, sr)

    grid = np.asarray([[0.0, 1.0], [0.5, 2.0], [1.0, 3.0], [1.5, 4.0]], dtype=float)
    monkeypatch.setattr(hybrid, "_run_madmom_dbn", lambda *_args, **_kwargs: grid.copy())
    blackboard, _ = _hybrid_blackboard(drums_path=drums_path)

    assert MadmomPrimarySegmentSpliceNode().execute(blackboard) == NodeStatus.SUCCESS

    beats = blackboard["beats"]
    assert beats[0, 0] == 0.0  # downbeat untouched despite the louder nearby transient
    assert abs(beats[1, 0] - 0.485) < 1.0 / sr  # beat 2 still snaps to real evidence
    report = blackboard["madmom_hybrid_report"]["micro_timing_snap_report"]
    assert report["downbeats_excluded"] is True
