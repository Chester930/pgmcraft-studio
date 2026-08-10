"""PASS-202: independent evidence consensus and phase arbitration."""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode
from pgm_craft.workflow.nodes import Blackboard


def test_nearby_candidates_from_independent_sources_are_aggregated():
    node = BarStartCandidateCommitNode()
    candidates, report = node._aggregate_consensus_candidates([
        {
            "candidate_id": "drum-1",
            "time": 12.30,
            "confidence": 0.65,
            "evidence_sources": ["kick"],
            "source_node": "DrumEvidenceBarSearchNode",
        },
        {
            "candidate_id": "bass-1",
            "time": 12.34,
            "confidence": 0.60,
            "evidence_sources": ["bass"],
            "source_node": "DrumBassEvidenceBarSearchNode",
        },
    ])
    assert report["triggered"] is True
    assert len(candidates) == 1
    assert candidates[0]["consensus_count"] == 2
    assert candidates[0]["confidence"] > 0.65
    assert 12.30 < candidates[0]["time"] < 12.34


def test_close_conflict_uses_committed_phase_consistency():
    node = BarStartCandidateCommitNode()
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", np.array([
        [0.0, 1], [1.0, 1], [2.0, 1],
    ], dtype=float))
    candidates = [
        {"candidate_id": "phase", "time": 3.0, "confidence": 0.71,
         "evidence_sources": ["drum"], "source_node": "drum"},
        {"candidate_id": "off", "time": 3.8, "confidence": 0.90,
         "evidence_sources": ["bass"], "source_node": "bass"},
    ]
    winner, report = node._best_candidate(
        candidates,
        committed_bar_starts=[0.0, 1.0, 2.0],
        blackboard=bb,
        return_arbitration=True,
    )
    assert report["triggered"] is True
    assert winner["time"] == 3.0
    assert report["winner_time"] == 3.0


def test_non_conflicting_candidates_keep_confidence_selection():
    node = BarStartCandidateCommitNode()
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", np.array([
        [0.0, 1], [1.0, 1],
    ], dtype=float))
    candidates = [
        {"candidate_id": "later", "time": 4.0, "confidence": 0.90,
         "evidence_sources": ["bass"], "source_node": "bass"},
        {"candidate_id": "next_bar", "time": 6.0, "confidence": 0.60,
         "evidence_sources": ["drum"], "source_node": "drum"},
    ]
    winner, report = node._best_candidate(
        candidates,
        committed_bar_starts=[0.0, 1.0],
        blackboard=bb,
        return_arbitration=True,
    )
    assert report["triggered"] is False
    assert winner["time"] == 4.0
