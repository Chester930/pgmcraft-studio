import unittest
import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import (
    SynthesizeRhythmTrackNode,
    PrepareInstrumentalTrackNode,
    TrackValidationNode,
    BeatFusionArbitratorNode,
    build_beat_tracking_tree,
    BeatTrackingBTEngine
)

class TestSDDPass23(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_sdd23_output"
        os.makedirs(self.test_dir, exist_ok=True)
        self.sr = 22050
        self.duration = 4.0  # 4 seconds
        
        # 模擬產生 drums.wav (在 1s, 2s 有打擊)
        self.drums_path = os.path.join(self.test_dir, "drums.wav")
        y_drums = np.zeros(int(self.sr * self.duration), dtype=np.float32)
        y_drums[int(1.0 * self.sr):int(1.05 * self.sr)] = 0.8
        y_drums[int(2.0 * self.sr):int(2.05 * self.sr)] = 0.8
        sf.write(self.drums_path, y_drums, self.sr)

        # 模擬產生 bass.wav (在 1s, 2s, 3s 有低音)
        self.bass_path = os.path.join(self.test_dir, "bass.wav")
        y_bass = np.zeros(int(self.sr * self.duration), dtype=np.float32)
        y_bass[int(1.0 * self.sr):int(1.1 * self.sr)] = 0.5
        y_bass[int(2.0 * self.sr):int(2.1 * self.sr)] = 0.5
        y_bass[int(3.0 * self.sr):int(3.1 * self.sr)] = 0.5
        sf.write(self.bass_path, y_bass, self.sr)

        # 模擬伴奏 no_vocals.wav (全區段有持續聲音)
        self.no_vocals_path = os.path.join(self.test_dir, "no_vocals.wav")
        y_inst = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.no_vocals_path, y_inst, self.sr)

    def test_synthesize_rhythm_and_prepare_inst_nodes(self):
        """測試 A 軌 rhythm 合成與 B 軌 prepare 節點"""
        bb = Blackboard()
        bb.set_val("stems", {"drums": self.drums_path, "bass": self.bass_path})
        bb.set_val("stems_dir", self.test_dir)

        node_a = SynthesizeRhythmTrackNode()
        status_a = node_a.execute(bb)
        self.assertEqual(status_a, NodeStatus.SUCCESS)
        rhythm_track = bb.get_val("rhythm_track_path")
        self.assertTrue(os.path.exists(rhythm_track))

        node_b = PrepareInstrumentalTrackNode()
        status_b = node_b.execute(bb)
        self.assertEqual(status_b, NodeStatus.SUCCESS)
        self.assertEqual(bb.get_val("inst_track_path"), self.no_vocals_path)

    def test_track_validation_node(self):
        """測試單軌信心度計算"""
        bb = Blackboard()
        beats = np.array([[1.0, 1], [1.5, 2], [2.0, 3], [2.5, 4]])
        bb.set_val("test_beats", beats)

        node = TrackValidationNode(beats_key="test_beats", conf_key="test_conf")
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertGreater(bb.get_val("test_conf"), 0.5)

    def test_beat_fusion_arbitrator_node(self):
        """測試雙軌融合仲裁衛兵在靜音段自動融合 B 軌"""
        bb = Blackboard()
        bb.set_val("rhythm_track_path", self.drums_path)
        
        # A 軌只有 1s, 2s (3s 靜音)
        beats_a = np.array([[1.0, 1], [2.0, 2]])
        # B 軌有 1s, 2s, 3s
        beats_b = np.array([[1.0, 1], [2.0, 2], [3.0, 3]])

        bb.set_val("beats_rhythm", beats_a)
        bb.set_val("beats_inst", beats_b)
        bb.set_val("conf_rhythm", 0.9)
        bb.set_val("conf_inst", 0.8)

        node = BeatFusionArbitratorNode(energy_threshold=0.05)
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        fused = bb.get_val("beats")
        self.assertIsNotNone(fused)
        report = bb.get_val("beat_fusion_report")
        self.assertIn("used_track_a_count", report)
        self.assertIn("switched_to_track_b_count", report)

    def test_full_stage3_bt_engine(self):
        """測試 Stage 3 BT Engine 完整樹鏈」"""
        bb = Blackboard()
        bb.set_val("stems", {"drums": self.drums_path, "bass": self.bass_path})
        bb.set_val("stems_dir", self.test_dir)
        bb.set_val("audio_path", "sample_test.wav")
        bb.set_val("beat_validation", {"status": "PASS"})

        engine = BeatTrackingBTEngine()
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("beat_tracking_status"), "SUCCESS")
        self.assertIsNotNone(result_bb.get_val("beats"))

if __name__ == "__main__":
    unittest.main()
