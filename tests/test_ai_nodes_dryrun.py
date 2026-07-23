"""
AI 節點 (CREPEPitchNode, BasicPitchNode, PodcastSpeechNode) 離線/Dry-Run 降級單元測試
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import CREPEPitchNode, BasicPitchNode, PodcastSpeechNode

class TestAINodesDryRun(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.audio_path = "sample_test.wav"
        self.assertTrue(os.path.exists(self.audio_path), "測試用 sample_test.wav 檔不存在")
        self.blackboard.set_val("audio_path", self.audio_path)
        self.blackboard.set_val("output_dir", self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('pgm_craft.workflow.audio_nodes.CREPEPitchNode._fallback_pitch_tracking')
    def test_crepe_pitch_node_fallback_execution(self, mock_fallback):
        """測試當 CREPE 推論引發例外時，CREPEPitchNode 自動觸發 Librosa pyin 備援並產出檔案"""
        mock_fallback.return_value = [
            {"time": 0.0, "freq_hz": 440.0, "confidence": 0.8},
            {"time": 0.5, "freq_hz": 440.0, "confidence": 0.8}
        ]
        
        # 透過強行使內部 raise Exception 模擬未安裝或執行失敗
        with patch('pgm_craft.workflow.audio_nodes.librosa.load', side_effect=Exception("Simulated CREPE/Librosa Offline")):
            node = CREPEPitchNode()
            status = node.execute(self.blackboard)
            
            self.assertEqual(status, NodeStatus.SUCCESS)
            vocal_midi = self.blackboard.get_val("vocal_pitch_midi")
            contour_json = self.blackboard.get_val("pitch_contour_json")
            self.assertIsNotNone(vocal_midi)
            self.assertIsNotNone(contour_json)
            self.assertTrue(os.path.exists(vocal_midi))
            self.assertTrue(os.path.exists(contour_json))

    def test_basic_pitch_node_fallback_execution(self):
        """測試當 basic_pitch 拋出例外時，BasicPitchNode 優雅退回 Librosa 樂譜估算"""
        with patch('pgm_craft.workflow.audio_nodes.BasicPitchNode._write_fallback_melody_midi') as mock_writer:
            def fake_write(beats, path):
                with open(path, "w") as f:
                    f.write("dummy midi")
            mock_writer.side_effect = fake_write
            
            node = BasicPitchNode()
            status = node.execute(self.blackboard)
            
            self.assertEqual(status, NodeStatus.SUCCESS)
            melody_midi = self.blackboard.get_val("melody_lead_midi")
            self.assertIsNotNone(melody_midi)
            self.assertTrue(os.path.exists(melody_midi))

    def test_podcast_speech_node_fallback_execution(self):
        """測試當 whisper 拋出例外時，PodcastSpeechNode 優雅退回備援能量診斷並產出字幕"""
        node = PodcastSpeechNode()
        with patch('pgm_craft.workflow.audio_nodes.PodcastSpeechNode._fallback_speech_segmentation') as mock_fallback:
            mock_fallback.return_value = [{"id": 1, "start": 0.0, "end": 2.0, "text": "[Speech Segment 01]"}]
            
            status = node.execute(self.blackboard)
            
            self.assertEqual(status, NodeStatus.SUCCESS)
            transcript_json = self.blackboard.get_val("transcript_json")
            subtitles_srt = self.blackboard.get_val("subtitles_srt")
            self.assertIsNotNone(transcript_json)
            self.assertIsNotNone(subtitles_srt)
            self.assertTrue(os.path.exists(transcript_json))
            self.assertTrue(os.path.exists(subtitles_srt))

if __name__ == '__main__':
    unittest.main()
