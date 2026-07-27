"""
SDD Pass 102 — 節拍與段落閉環對齊驗證衛兵 (BeatAlignmentVerifierGuardNode) 與鼓組 Fallback 重算單元測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import (
    BeatAlignmentVerifierGuardNode,
    DrumsKickBeatFallbackNode,
    build_beat_tracking_tree
)


class TestSDDPass102BeatAlignmentVerification(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.temp_dir, "beat_test.wav")
        sr = 22050
        t = np.linspace(0, 2.0, sr * 2, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.audio_path, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_verifier_passes_when_aligned(self):
        """驗證 BeatAlignmentVerifierGuardNode 在節拍與段落完全對齊時傳回 NodeStatus.SUCCESS」"""
        bb = Blackboard()
        bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1]]))
        bb.set_val("sections", [{"start_time": 0.0, "name": "Intro"}, {"start_time": 2.0, "name": "Verse"}])
        bb.set_val("kick_anchors", np.array([0.0, 1.0, 2.0]))

        node = BeatAlignmentVerifierGuardNode(confidence_threshold=0.70)
        status = node.run(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertGreaterEqual(bb.get_val("beat_alignment_score"), 0.70)

    def test_verifier_fails_and_triggers_fallback(self):
        """驗證 BeatAlignmentVerifierGuardNode 在對齊偏離時傳回 NodeStatus.FAILURE 並由 Fallback 校正」"""
        bb = Blackboard()
        # 設定錯位的 beats（例如 Downbeat 落在 0.33，與 Section 0.0, 2.0 嚴重的對不上）
        bb.set_val("beats", np.array([[0.33, 2], [0.83, 3], [1.33, 4], [1.83, 1]]))
        bb.set_val("sections", [{"start_time": 0.0, "name": "Intro"}, {"start_time": 2.0, "name": "Verse"}])
        bb.set_val("kick_anchors", np.array([0.0, 2.0]))
        bb.set_val("audio_path", self.audio_path)

        verifier = BeatAlignmentVerifierGuardNode(confidence_threshold=0.70)
        status_verifier = verifier.run(bb)
        self.assertEqual(status_verifier, NodeStatus.FAILURE)

        # 執行 Fallback 重新校正
        fallback = DrumsKickBeatFallbackNode()
        status_fallback = fallback.run(bb)
        self.assertEqual(status_fallback, NodeStatus.SUCCESS)
        self.assertTrue(bb.get_val("fallback_beat_recalculated"))

    def test_build_beat_tracking_tree_includes_verifier(self):
        """驗證 build_beat_tracking_tree 的根節點包含閉環對齊驗證與 Fallback 節點」"""
        tree = build_beat_tracking_tree()
        self.assertIsNotNone(tree)
        # 尋找 BeatAlignmentVerificationAndFallback 節點
        child_names = [child.name for child in tree.children]
        self.assertIn("BeatAlignmentVerificationAndFallback", child_names)


if __name__ == "__main__":
    unittest.main()
