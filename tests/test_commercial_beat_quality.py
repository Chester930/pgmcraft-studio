import os

import numpy as np
import soundfile as sf

from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.workflow.beat_tracking_bt import (
    BeatGridContinuityRepairNode,
    CommercialBeatQualityNode,
    DownbeatPhaseConsistencyNode,
    DrumsKickBeatFallbackNode,
    KickAnchorConsensusSnapNode,
    TempoOscillationDampingNode,
    build_beat_tracking_tree,
)
from pgm_craft.workflow.nodes import Blackboard


def test_drum_fallback_keeps_higher_quality_existing_beats(tmp_path):
    audio_path = tmp_path / "sparse_drum.wav"
    sr = 22050
    duration = 3.0
    y = np.zeros(int(sr * duration), dtype=np.float32)
    for t in [0.0, 1.0, 2.0]:
        idx = int(t * sr)
        y[idx:idx + 80] = 0.8
    sf.write(audio_path, y, sr)

    existing = np.array([
        [0.0, 1],
        [0.5, 2],
        [1.0, 3],
        [1.5, 4],
        [2.0, 1],
        [2.5, 2],
    ], dtype=float)

    bb = Blackboard()
    bb.set_val("beats", existing.copy())
    bb.set_val("refined_beats", existing.copy())
    bb.set_val("audio_path", str(audio_path))
    bb.set_val("kick_anchors", np.array([0.0, 1.0, 2.0]))
    bb.set_val("beat_alignment_score", 0.68)

    status = DrumsKickBeatFallbackNode(min_quality_improvement=8.0).execute(bb)

    assert status.name == "SUCCESS"
    assert bb.get_val("fallback_beat_recalculated") is False
    assert bb.get_val("fallback_beat_rejected") is True
    np.testing.assert_array_equal(bb.get_val("beats"), existing)


def test_beat_grid_repair_inserts_missing_transition_beat():
    bb = Blackboard()
    beats = np.array([
        [0.0, 1],
        [0.5, 2],
        [1.5, 4],
        [2.0, 1],
    ], dtype=float)
    bb.set_val("beats", beats)

    status = BeatGridContinuityRepairNode().execute(bb)

    assert status.name == "SUCCESS"
    repaired = bb.get_val("beats")
    assert len(repaired) == 5
    np.testing.assert_allclose(repaired[:, 0], [0.0, 0.5, 1.0, 1.5, 2.0], atol=1e-6)
    np.testing.assert_array_equal(repaired[:, 1], [1, 2, 3, 4, 1])
    assert bb.get_val("beat_grid_repair_report")["inserted_count"] == 1


def test_downbeat_phase_consistency_relabels_section_aligned_phase():
    bb = Blackboard()
    beats = np.array([
        [0.0, 2],
        [0.5, 3],
        [1.0, 4],
        [1.5, 1],
        [2.0, 2],
        [2.5, 3],
        [3.0, 4],
        [3.5, 1],
    ], dtype=float)
    bb.set_val("beats", beats)
    bb.set_val("sections", [{"start_time": 0.0, "name": "Intro"}, {"start_time": 2.0, "name": "Verse"}])
    bb.set_val("kick_anchors", np.array([0.0, 2.0]))

    status = DownbeatPhaseConsistencyNode().execute(bb)

    assert status.name == "SUCCESS"
    relabeled = bb.get_val("beats")
    np.testing.assert_array_equal(relabeled[:, 1], [1, 2, 3, 4, 1, 2, 3, 4])
    assert bb.get_val("downbeat_phase_report")["status"] == "RELABELED"


def test_kick_anchor_consensus_snap_applies_only_when_grid_quality_improves():
    bb = Blackboard()
    beats = np.array([
        [0.04, 1],
        [0.5, 2],
        [1.04, 3],
        [1.5, 4],
        [2.04, 1],
        [2.5, 2],
    ], dtype=float)
    bb.set_val("beats", beats)
    bb.set_val("kick_anchors", np.array([0.0, 1.0, 2.0]))

    status = KickAnchorConsensusSnapNode(min_quality_improvement=1.0).execute(bb)

    assert status.name == "SUCCESS"
    snapped = bb.get_val("beats")
    np.testing.assert_allclose(snapped[[0, 2, 4], 0], [0.0, 1.0, 2.0], atol=1e-6)
    assert bb.get_val("kick_anchor_snap_report")["status"] == "APPLIED"


def test_tempo_oscillation_damping_repairs_fast_slow_reversal():
    bb = Blackboard()
    beats = np.array([
        [0.0, 1],
        [0.5, 2],
        [1.0, 3],
        [1.25, 4],
        [2.0, 1],
        [2.5, 2],
        [3.0, 3],
        [3.5, 4],
        [4.0, 1],
    ], dtype=float)
    bb.set_val("beats", beats)

    status = TempoOscillationDampingNode(edge_beat_guard=2, min_quality_improvement=0.5).execute(bb)

    assert status.name == "SUCCESS"
    damped = bb.get_val("beats")
    np.testing.assert_allclose(damped[:, 0], np.arange(0.0, 4.5, 0.5), atol=1e-6)
    report = bb.get_val("tempo_oscillation_report")
    assert report["status"] == "DAMPED"
    assert report["corrected_count"] == 1


def test_tempo_oscillation_damping_preserves_gradual_tempo_change():
    bb = Blackboard()
    times = np.array([0.0, 0.58, 1.13, 1.65, 2.14, 2.60, 3.03, 3.43, 3.80])
    beats = np.column_stack([times, (np.arange(len(times)) % 4) + 1]).astype(float)
    bb.set_val("beats", beats)

    status = TempoOscillationDampingNode(edge_beat_guard=1).execute(bb)

    assert status.name == "SUCCESS"
    np.testing.assert_array_equal(bb.get_val("beats"), beats)
    assert bb.get_val("tempo_oscillation_report")["status"] == "PASS"


def test_tempo_oscillation_damping_skips_edges_and_exclusion_zones():
    bb = Blackboard()
    beats = np.array([
        [0.0, 1],
        [0.25, 2],
        [1.0, 3],
        [1.5, 4],
        [2.0, 1],
        [2.25, 2],
        [3.0, 3],
        [3.5, 4],
        [4.0, 1],
    ], dtype=float)
    bb.set_val("beats", beats.copy())
    bb.set_val("snap_exclusion_zones", [{"start_time": 1.95, "end_time": 2.55, "reason": "dramatic_transition"}])

    status = TempoOscillationDampingNode(edge_beat_guard=2).execute(bb)

    assert status.name == "SUCCESS"
    np.testing.assert_array_equal(bb.get_val("beats"), beats)
    report = bb.get_val("tempo_oscillation_report")
    assert report["status"] == "PASS"
    assert report["skipped_edge_count"] >= 1
    assert report["skipped_exclusion_count"] >= 1


def test_commercial_quality_node_scores_release_ready_grid():
    bb = Blackboard()
    beats = np.array([[i * 0.5, (i % 4) + 1] for i in range(16)], dtype=float)
    bb.set_val("beats", beats)
    bb.set_val("refined_beats", beats)
    bb.set_val("beat_validation", {"status": "PASS", "warnings": []})
    bb.set_val("beat_alignment_score", 0.98)
    bb.set_val("phase_realignment_report", {"adjusted_count": 16, "total_beats": 16})
    bb.set_val("snap_offsets_ms", [1.0, -2.0, 3.0, -1.0])
    bb.set_val("smoothing_report", {"outlier_count": 0})

    status = CommercialBeatQualityNode(commercial_threshold=98.0).execute(bb)

    assert status.name == "SUCCESS"
    report = bb.get_val("commercial_beat_quality")
    assert report["score"] >= 98.0
    assert report["status"] == "COMMERCIAL_READY"


def test_beat_tracking_tree_contains_commercial_quality_node():
    names = [child.name for child in build_beat_tracking_tree().children]

    assert "BeatGridContinuityRepairNode" in names
    assert "DownbeatPhaseConsistencyNode" in names
    assert "KickAnchorConsensusSnapNode" in names
    assert "TempoOscillationDampingNode" in names
    assert "CommercialBeatQualityNode" in names
    assert names.index("ViterbiTempoSmoothingNode") < names.index("BeatGridContinuityRepairNode")
    assert names.index("BeatGridContinuityRepairNode") < names.index("TempoOscillationDampingNode")
    assert names.index("TempoOscillationDampingNode") < names.index("DownbeatPhaseConsistencyNode")
    assert names.index("DownbeatPhaseConsistencyNode") < names.index("KickAnchorConsensusSnapNode")
    assert names.index("KickAnchorConsensusSnapNode") < names.index("BeatAlignmentVerificationAndFallback")
    assert names.index("BeatAlignmentVerificationAndFallback") < names.index("CommercialBeatQualityNode")


def test_pipeline_report_includes_commercial_quality(tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fixture")
    beats = np.array([[i * 0.5, (i % 4) + 1] for i in range(8)], dtype=float)

    bb = Blackboard()
    bb.set_val("beats", beats)
    bb.set_val("refined_beats", beats)
    bb.set_val("workflow_status", "SUCCESS")
    bb.set_val("commercial_beat_quality", {"score": 91.0, "status": "REVIEW_REQUIRED"})

    engine = PGMCraftEngine(enable_stem_separation=False)
    engine.bt_engine.run = lambda *args, **kwargs: bb

    report = engine.run(str(audio_path), output_dir=str(tmp_path), target_stage="stage3")

    assert report["commercial_beat_quality"]["score"] == 91.0
