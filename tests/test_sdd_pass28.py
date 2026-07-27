import unittest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import (
    TrackValidationNode,
    BeatFusionArbitratorNode,
    build_beat_tracking_tree
)
from pgm_craft.workflow.audio_nodes import DownbeatRefineNode

class TestSDDPass28(unittest.TestCase):
    def test_track_validation_dimension_guard(self):
        """測試 TrackValidationNode 對於 1D 或極端空陣列的防護」"""
        bb = Blackboard()
        # 傳入無效 1D 陣列
        bb.set_val("beats_rhythm", np.array([1.0, 2.0, 3.0]))

        node = TrackValidationNode(beats_key="beats_rhythm", conf_key="conf_rhythm")
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(bb.get_val("conf_rhythm"), 0.0)

    def test_downbeat_refine_count_in_anchor(self):
        """測試 DownbeatRefineNode 利用 count-in 喊拍事件錨定小節第一拍」"""
        bb = Blackboard()
        # 模擬 8 拍無 downbeat 標籤 (全為 0)
        beats = np.array([
            [0.5, 0], [1.0, 0], [1.5, 0], [2.0, 0],
            [2.5, 0], [3.0, 0], [3.5, 0], [4.0, 0]
        ])
        bb.set_val("beats", beats)
        # 喊拍 event 在 t=1.0 結束（對應索引 1 的第 1 拍）
        bb.set_val("count_in_events", [{"time": 1.0, "type": "count_in_4"}])

        node = DownbeatRefineNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        refined = bb.get_val("refined_beats")
        self.assertIsNotNone(refined)
        # 索引 1 (t=1.0) 應被成功錨定為 1 拍 (Downbeat)
        self.assertEqual(int(refined[1, 1]), 1)

    def test_beat_fusion_memory_cache(self):
        """測試 BeatFusionArbitratorNode 優先使用 Blackboard 記憶體音訊緩存」"""
        bb = Blackboard()
        beats_a = np.array([[0.0, 1], [0.5, 2], [1.0, 3]])
        beats_b = np.array([[0.0, 1], [0.5, 2], [1.0, 3]])
        bb.set_val("beats_rhythm", beats_a)
        bb.set_val("beats_inst", beats_b)
        
        # 提供記憶體緩存音訊
        sr = 22050
        y_dummy = np.zeros(sr * 2, dtype=np.float32)
        bb.set_val("y_rhythm", y_dummy)
        bb.set_val("sr_rhythm", sr)

        node = BeatFusionArbitratorNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(bb.get_val("beats"))

if __name__ == "__main__":
    unittest.main()
