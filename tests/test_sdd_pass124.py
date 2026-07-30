"""
SDD Pass 124 — Module 3 BarStart v2: commit-time quality gate on
`BarStartCandidateCommitNode`, ported from Stage 3's
`KickAnchorConsensusSnapNode` "score before/after, only accept if it wins"
pattern.

v2 previously committed a candidate purely on `confidence >= threshold`. A
confidently-detected candidate can still be badly timed relative to the
already-committed bars (e.g. a stray high-confidence onset half a beat off).
This pass adds a lightweight bar-duration-consistency score
(`_score_bar_start_list_quality`) and rejects a commit that would make the
bar list meaningfully less regular than it already is -- recording it as
`quality_regression` in `unresolved_bar_spans` instead of silently
committing.
"""

import unittest

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    _score_bar_start_list_quality,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass124CommitQualityGate(unittest.TestCase):
    def test_score_helper_returns_none_below_three_bars(self):
        self.assertIsNone(_score_bar_start_list_quality([0.0]))
        self.assertIsNone(_score_bar_start_list_quality([0.0, 2.0]))

    def test_score_helper_scores_regular_bars_near_one(self):
        score = _score_bar_start_list_quality([0.0, 2.0, 4.0, 6.0])
        self.assertGreater(score, 0.95)

    def test_score_helper_penalizes_irregular_bars(self):
        regular = _score_bar_start_list_quality([0.0, 2.0, 4.0, 6.0])
        irregular = _score_bar_start_list_quality([0.0, 2.0, 4.0, 4.9])
        self.assertLess(irregular, regular)

    def test_high_confidence_candidate_that_wrecks_grid_regularity_is_rejected(self):
        bb = Blackboard()
        # three prior bars are perfectly regular (2.0s each)
        bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0])
        bb.set_val("active_bar_probe_window", {"start_time": 4.0, "end_time": 9.0})
        # a high-confidence candidate lands far too early (0.4s bar) despite winning on confidence
        bb.set_val("bar_start_candidates", [
            {"time": 4.4, "confidence": 0.95, "evidence_sources": ["stray_onset"]},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        # commit must be rejected: the bar list must stay untouched
        self.assertEqual(bb.get_val("committed_bar_starts"), [0.0, 2.0, 4.0])
        report = bb.get_val("bar_start_decision_report")
        self.assertEqual(report["status"], "UNRESOLVED")
        self.assertEqual(report["reason"], "quality_regression")
        self.assertIsNotNone(report["quality_before"])
        self.assertLess(report["quality_after"], report["quality_before"])

        unresolved = bb.get_val("unresolved_bar_spans")
        self.assertEqual(unresolved[-1]["reason"], "quality_regression")
        self.assertEqual(unresolved[-1]["rejected_time"], 4.4)

    def test_high_confidence_candidate_that_preserves_grid_regularity_is_committed(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0])
        bb.set_val("active_bar_probe_window", {"start_time": 4.0, "end_time": 9.0})
        bb.set_val("bar_start_candidates", [
            {"time": 6.0, "confidence": 0.9, "evidence_sources": ["drums", "bass"]},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        self.assertEqual(bb.get_val("committed_bar_starts"), [0.0, 2.0, 4.0, 6.0])
        report = bb.get_val("bar_start_decision_report")
        self.assertEqual(report["status"], "COMMITTED")
        self.assertGreaterEqual(report["quality_after"], report["quality_before"])

    def test_quality_gate_is_skipped_gracefully_with_fewer_than_three_prior_bars(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
        bb.set_val("bar_start_candidates", [
            {"time": 4.4, "confidence": 0.9, "evidence_sources": ["drums"]},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        self.assertEqual(bb.get_val("committed_bar_starts"), [0.0, 2.0, 4.4])
        self.assertEqual(bb.get_val("bar_start_decision_report")["status"], "COMMITTED")


if __name__ == "__main__":
    unittest.main()
