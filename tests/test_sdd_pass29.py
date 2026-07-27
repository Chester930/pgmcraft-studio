import unittest
import os
import shutil
import tempfile
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.export_bt import (
    MIDIMarkerSectionExportNode,
    build_export_tree,
    ExportBTEngine
)

class TestSDDPass29(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sections = [
            {"measure": 1, "name": "Intro", "start_time": 0.0},
            {"measure": 5, "name": "Verse 1", "start_time": 8.0},
            {"measure": 13, "name": "Chorus 1", "start_time": 24.0},
            {"measure": 21, "name": "Outro", "start_time": 40.0}
        ]
        self.beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4],
            [4.0, 1], [4.5, 2], [5.0, 3], [5.5, 4]
        ])

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_midi_marker_section_export_node(self):
        """測試 MIDIMarkerSectionExportNode 生成段落 Marker MIDI"""
        bb = Blackboard()
        bb.set_val("sections", self.sections)
        bb.set_val("beats", self.beats)
        bb.set_val("output_dir", self.test_dir)

        node = MIDIMarkerSectionExportNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        marker_midi = bb.get_val("section_markers_midi")
        self.assertIsNotNone(marker_midi)
        self.assertTrue(os.path.exists(marker_midi))

    def test_export_bt_engine(self):
        """測試 Stage 5 ExportBT 完整樹鏈執行」"""
        bb = Blackboard()
        bb.set_val("audio_path", "sample_test.wav")
        bb.set_val("beats", self.beats)
        bb.set_val("sections", self.sections)
        bb.set_val("output_dir", self.test_dir)

        engine = ExportBTEngine()
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("export_status"), "SUCCESS")

        # 驗證導出素材路徑
        self.assertIsNotNone(result_bb.get_val("click_track"))
        self.assertIsNotNone(result_bb.get_val("tempo_map_midi"))
        self.assertIsNotNone(result_bb.get_val("section_markers_midi"))

if __name__ == "__main__":
    unittest.main()
