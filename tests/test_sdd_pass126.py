"""
SDD Pass 126 — Module 3 BarStart v2: the missing full-song walking loop.

Every node in the probe/commit ladder (RollingProbeWindowNode through
BarStartCandidateCommitNode, Pass 105-117) was built and unit-tested one
probe window at a time. Nothing outside those nodes ever re-invoked the
ladder, so a single `build_module3_barstart_v2_pipeline_tree()` run only ever
committed at most one bar past the seed -- nowhere near enough to cover a
whole song. `FullSongBarStartLoopNode` is the outer driver that was missing.
"""

import unittest

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import FullSongBarStartLoopNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


class TestSDDPass126FullSongLoop(unittest.TestCase):
    def test_v2_pipeline_wraps_the_probe_ladder_in_the_loop_node(self):
        names = _node_names(build_master_pipeline_tree(target_stage="module3_barstart_v2"))
        self.assertIn("FullSongBarStartLoopNode", names)
        self.assertIn("BarStartV2ProbeTick", names)
        for inner in ["RollingProbeWindowNode", "DrumEvidenceBarSearchNode", "ReliableBarAnchorNode", "BarStartCandidateCommitNode"]:
            self.assertIn(inner, names)
            self.assertLess(names.index("FullSongBarStartLoopNode"), names.index(inner))
        # relative order inside the tick is unchanged from Pass 105-117
        self.assertLess(names.index("DrumEvidenceBarSearchNode"), names.index("ReliableBarAnchorNode"))
        self.assertLess(names.index("ReliableBarAnchorNode"), names.index("BarStartCandidateCommitNode"))
        # the loop node still precedes the one-shot post-loop nodes
        self.assertLess(names.index("BarStartCandidateCommitNode"), names.index("BarGridContinuityRepairNode"))
        self.assertLess(names.index("BarGridContinuityRepairNode"), names.index("MeterAwareBeatGridNode"))

    def test_loop_walks_the_whole_song_via_stall_recovery_and_stops_at_duration(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("audio_duration_sec", 20.0)
        # no drum/bass/chord/melody/beat_this evidence at all -> every tick's
        # commit attempt fails, forcing repeated stall-recovery via the
        # NoDrumPhaseCarryNode fallback (Pass 125) at the default 120bpm/4:4 pace.
        status = FullSongBarStartLoopNode(max_iterations=100, stall_limit=2).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("full_song_loop_report")
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["stop_reason"], "reached_audio_duration")
        self.assertGreaterEqual(report["stall_recoveries"], 1)
        self.assertLess(report["iterations"], 100)

        bars = bb.get_val("committed_bar_starts")
        self.assertEqual(bars, sorted(bars))
        self.assertEqual(len(set(bars)), len(bars))
        self.assertGreaterEqual(bars[-1], 20.0 - 0.5)
        self.assertLessEqual(bars[-1], 20.0 + 2.0)
        self.assertEqual(report["committed_bar_count"], len(bars))

    def test_loop_stops_gracefully_when_bar_duration_cannot_be_resolved(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("tempo_bpm", 0)  # forces NoDrumPhaseCarryNode's bar_duration to 0.0
        bb.set_val("meter_profile", {"beats_per_bar": 4})
        status = FullSongBarStartLoopNode(max_iterations=50, stall_limit=2).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("full_song_loop_report")
        self.assertEqual(report["stop_reason"], "stalled_no_recovery")
        self.assertLess(report["iterations"], 50)
        self.assertEqual(report["stall_recoveries"], 0)
        # nothing was fabricated in place of real evidence
        self.assertEqual(bb.get_val("committed_bar_starts"), [0.0, 2.0])

    def test_loop_respects_max_iterations_safety_cap_when_nothing_bounds_it(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        # no audio_duration_sec, no y/sr -> unbounded fallback recovery forever
        status = FullSongBarStartLoopNode(max_iterations=6, stall_limit=2).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("full_song_loop_report")
        self.assertEqual(report["status"], "MAX_ITERATIONS_REACHED")
        self.assertEqual(report["stop_reason"], "max_iterations_reached")
        self.assertEqual(report["iterations"], 6)
        self.assertGreater(report["stall_recoveries"], 0)


if __name__ == "__main__":
    unittest.main()
