"""
SDD Pass 122 — Module 3 BarStart v2: quantified 0-100 quality score as an
auxiliary metric alongside the pass/fail `promotion_gate`.

Reuses Stage 3's `_score_beat_grid_quality` pure function on the finalized
beat matrix, then layers v2-specific penalties: unresolved bar probe spans, a
structurally repaired bar grid, and a downbeat rotation from the low-frequency
verifier.
"""

import unittest

import numpy as np

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartV2QualityScoreNode,
    Module3BarStartV2SummaryNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def _clean_beats(n_bars=8):
    rows = []
    for bar in range(n_bars):
        for beat in range(4):
            t = bar * 2.0 + beat * 0.5
            rows.append([t, beat + 1])
    return np.asarray(rows, dtype=float)


class TestSDDPass122QualityScore(unittest.TestCase):
    def test_v2_pipeline_places_quality_score_before_click_synthesis(self):
        names = _node_names(build_master_pipeline_tree(target_stage="module3_barstart_v2"))
        self.assertIn("BarStartV2QualityScoreNode", names)
        self.assertLess(
            names.index("KickBassDownbeatVerifierNode"),
            names.index("BarStartV2QualityScoreNode"),
        )
        self.assertLess(
            names.index("BarStartV2QualityScoreNode"),
            names.index("ClickSynthesisNode"),
        )

    def test_clean_grid_scores_high_with_no_warnings(self):
        bb = Blackboard()
        bb.set_val("beats", _clean_beats())
        status = BarStartV2QualityScoreNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        result = bb.get_val("barstart_v2_quality_score")
        self.assertGreater(result["score"], 80.0)
        self.assertEqual(result["warnings"], [])

    def test_unresolved_spans_and_repairs_reduce_score_with_warnings(self):
        bb = Blackboard()
        bb.set_val("beats", _clean_beats())
        bb.set_val("unresolved_bar_spans", [{"start_time": 4.0, "end_time": 6.0}])
        bb.set_val("bar_grid_repair_report", {
            "status": "REPAIRED",
            "inserted_bar_count": 1,
            "removed_bar_count": 0,
            "oscillation_damped_count": 1,
        })
        bb.set_val("downbeat_fix_report", {"status": "ROTATED", "rotated_beat_count": 2})

        clean_score = BarStartV2QualityScoreNode()
        clean_bb = Blackboard()
        clean_bb.set_val("beats", _clean_beats())
        clean_score.execute(clean_bb)
        clean_result = clean_bb.get_val("barstart_v2_quality_score")

        status = BarStartV2QualityScoreNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        result = bb.get_val("barstart_v2_quality_score")

        self.assertLess(result["score"], clean_result["score"])
        self.assertIn("unresolved_bar_spans=1", result["warnings"])
        self.assertIn("bar_grid_repairs=2", result["warnings"])
        self.assertIn("downbeat_rotated_by_low_freq_verifier", result["warnings"])

    def test_summary_carries_quality_score_into_report(self):
        bb = Blackboard()
        bb.set_val("barstart_v2_quality_score", {"score": 91.5, "warnings": []})
        self.assertEqual(Module3BarStartV2SummaryNode().execute(bb), NodeStatus.SUCCESS)
        report = bb.get_val("barstart_v2_report")
        self.assertEqual(report["quality_score"]["score"], 91.5)
        self.assertEqual(report["status"], "EXPERIMENTAL_PASS_125")


if __name__ == "__main__":
    unittest.main()
