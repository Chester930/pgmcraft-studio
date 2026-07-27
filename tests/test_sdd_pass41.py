import unittest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import ReEntryReAnchoringNode

class TestSDDPass41(unittest.TestCase):
    def setUp(self):
        self.blackboard = Blackboard()
        # 模擬一組拍點：前段在 t=2.0s 處從無鼓區切回有鼓區，但原本標記錯把 t=2.0s 當成第 3 拍
        beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], # 第一小節
            [2.0, 3], [2.5, 4], [3.0, 1], [3.5, 2]  # 重返點 t=2.0s 被錯當成 3 拍
        ])
        
        # 第一聲 Kick 撞擊脈衝剛好出現在 t=2.0s
        kick_anchors = np.array([0.0, 2.0])
        
        self.blackboard.set_val("beats", beats)
        self.blackboard.set_val("kick_anchors", kick_anchors)

    def test_reentry_reanchoring_forces_downbeat_one(self):
        """驗證 ReEntryReAnchoringNode 能在鼓聲切入點強行將重音錨定為 Beat 1」"""
        node = ReEntryReAnchoringNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        reanchored_beats = self.blackboard.get_val("beats")
        self.assertIsNotNone(reanchored_beats)
        
        # 找 t=2.0s 的列，其拍號標記必須被校正重錨為 1
        t_2_row = [r for r in reanchored_beats if abs(r[0] - 2.0) < 0.1]
        self.assertGreater(len(t_2_row), 0)
        self.assertEqual(int(t_2_row[0][1]), 1)

if __name__ == "__main__":
    unittest.main()
