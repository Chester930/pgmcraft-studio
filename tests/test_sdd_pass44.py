import unittest
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import DownbeatAlignedSectionNode

class TestSDDPass44(unittest.TestCase):
    def setUp(self):
        self.blackboard = Blackboard()
        
        # 小節映射表：1 號拍時間分別為 0.0s, 2.0s, 4.0s, 6.0s, 8.0s, 10.0s, 12.0s, 14.0s, 16.0s
        measure_map = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0},
            {"measure": 2, "start_time": 2.0, "end_time": 4.0},
            {"measure": 3, "start_time": 4.0, "end_time": 6.0},
            {"measure": 4, "start_time": 6.0, "end_time": 8.0},
            {"measure": 5, "start_time": 8.0, "end_time": 10.0},
            {"measure": 6, "start_time": 10.0, "end_time": 12.0},
            {"measure": 7, "start_time": 12.0, "end_time": 14.0},
            {"measure": 8, "start_time": 14.0, "end_time": 16.0}
        ]
        
        # 模擬原版切在中間拍的 Section (例如 Intro 結束在 7.8s，Chorus 開始在 15.7s)
        sections = [
            {"name": "Intro", "start_time": 0.0, "end_time": 7.8, "measure": 1},
            {"name": "Verse", "start_time": 7.8, "end_time": 15.7, "measure": 5},
            {"name": "Chorus", "start_time": 15.7, "end_time": 16.0, "measure": 9}
        ]
        
        self.blackboard.set_val("measure_map", measure_map)
        self.blackboard.set_val("sections", sections)

    def test_downbeat_aligned_section_node_snaps_to_downbeats(self):
        """驗證 DownbeatAlignedSectionNode 能將樂段邊界強行吸附至小節第一拍」"""
        node = DownbeatAlignedSectionNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        aligned_sections = self.blackboard.get_val("sections")
        self.assertIsNotNone(aligned_sections)
        
        # 7.8s 應被吸附對齊至小節第 1 拍 8.0s
        self.assertAlmostEqual(aligned_sections[0]["end_time"], 8.0, delta=0.1)
        self.assertAlmostEqual(aligned_sections[1]["start_time"], 8.0, delta=0.1)
        # 15.7s 應被吸附對齊至小節第 1 拍 16.0s
        self.assertAlmostEqual(aligned_sections[1]["end_time"], 16.0, delta=0.1)

if __name__ == "__main__":
    unittest.main()
