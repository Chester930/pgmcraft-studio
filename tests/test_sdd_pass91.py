"""
SDD Pass 91 — 動態變拍號 (Meter Change Detection) 與 3/4, 6/8 拍號自動切換衛兵單元測試
"""

import os
import tempfile
import unittest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.music_analysis_bt import DynamicMeterChangeGuardNode


class TestSDDPass91DynamicMeterChangeGuard(unittest.TestCase):

    def test_dynamic_meter_change_detection(self):
        """驗證 DynamicMeterChangeGuardNode 成功檢測 4/4 拍與 3/4 拍轉換點」"""
        blackboard = Blackboard()
        # 前段 4/4 拍 (每小節 4 拍)，後段 3/4 拍 (每小節 3 拍)
        beats = np.array([
            [0.0, 1], [0.5, 0], [1.0, 0], [1.5, 0],
            [2.0, 1], [2.5, 0], [3.0, 0], [3.5, 0],
            [4.0, 1], [4.5, 0], [5.0, 0],          # 轉換為 3/4 拍
            [5.5, 1], [6.0, 0], [6.5, 0],
            [7.0, 1]
        ])
        blackboard.set_val("beats", beats)

        node = DynamicMeterChangeGuardNode()
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        changes = blackboard.get_val("meter_changes")
        self.assertIsNotNone(changes)
        self.assertGreaterEqual(len(changes), 1)


if __name__ == "__main__":
    unittest.main()
