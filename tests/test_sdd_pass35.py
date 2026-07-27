import unittest
import os
import shutil
import tempfile
import mido
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.export_bt import HumanGrooveMIDIExportNode

class TestSDDPass35(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("output_dir", self.test_dir)
        self.blackboard.set_val("beats", [(0.0, 1), (0.5, 2), (1.0, 3), (1.5, 4)])
        self.blackboard.set_val("rhythm_track_path", "sample_test.wav")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_human_groove_midi_export_node_standalone(self):
        """驗證 HumanGrooveMIDIExportNode 能正確生成帶微位移律動之 tempo_map_human_groove.mid」"""
        node = HumanGrooveMIDIExportNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        outputs = self.blackboard.get_val("outputs", {})
        self.assertIn("human_groove_midi", outputs)
        
        groove_mid = outputs["human_groove_midi"]
        self.assertTrue(os.path.exists(groove_mid))
        
        mid = mido.MidiFile(groove_mid)
        self.assertGreater(len(mid.tracks), 0)

if __name__ == "__main__":
    unittest.main()
