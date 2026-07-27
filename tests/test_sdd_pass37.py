import unittest
import os
import shutil
import tempfile
import mido
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.export_bt import MIDILyricsMarkerExportNode

class TestSDDPass37(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("output_dir", self.test_dir)
        self.blackboard.set_val("subtitles_srt", "1\n00:00:00,000 --> 00:00:02,000\nVerse 1 Lyrics Line 1")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_midi_lyrics_marker_export_node_standalone(self):
        """驗證 MIDILyricsMarkerExportNode 能正確匯出包含歌詞 Marker 之 lyrics_markers.mid」"""
        node = MIDILyricsMarkerExportNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        outputs = self.blackboard.get_val("outputs", {})
        self.assertIn("lyrics_markers_midi", outputs)
        
        lyrics_mid = outputs["lyrics_markers_midi"]
        self.assertTrue(os.path.exists(lyrics_mid))
        
        mid = mido.MidiFile(lyrics_mid)
        self.assertGreater(len(mid.tracks), 0)

if __name__ == "__main__":
    unittest.main()
