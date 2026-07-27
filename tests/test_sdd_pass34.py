import unittest
import os
import shutil
import tempfile
import mido
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.export_bt import MIDIExportNode

class TestSDDPass34(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("output_dir", self.test_dir)
        self.blackboard.set_val("beats", [(0.0, 1), (0.5, 2), (1.0, 3), (1.5, 4)])
        self.blackboard.set_val("pitch_contour", [
            {"time": 0.0, "pitch": 60.0},
            {"time": 0.5, "pitch": 62.0},
            {"time": 1.0, "pitch": 64.0}
        ])

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_midi_export_node_bass_and_lead_melody(self):
        """驗證 MIDIExportNode 能正確導出 bass_line.mid 與 lead_melody.mid」"""
        node = MIDIExportNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        outputs = self.blackboard.get_val("outputs", {})
        self.assertIn("bass_line_midi", outputs)
        self.assertIn("lead_melody_midi", outputs)
        
        bass_mid = outputs["bass_line_midi"]
        lead_mid = outputs["lead_melody_midi"]
        
        self.assertTrue(os.path.exists(bass_mid))
        self.assertTrue(os.path.exists(lead_mid))
        
        mid = mido.MidiFile(lead_mid)
        self.assertGreater(len(mid.tracks), 0)

if __name__ == "__main__":
    unittest.main()
