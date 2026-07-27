"""
SDD Pass 101 — FullAutoDemixingBTEngine 純伴奏與 Click 混音導出節點 (SynthesizeFullAutoBackingNode) 單元測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.full_auto_bt import SynthesizeFullAutoBackingNode, FullAutoDemixingBTEngine


class TestSDDPass101FullAutoBackingSynthesis(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.temp_dir, "test_input.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.audio_path, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_synthesize_full_auto_backing_node_direct(self):
        """驗證 SynthesizeFullAutoBackingNode 成功匯出 backing.wav 與 backing_with_click.wav」"""
        bb = Blackboard()
        bb.set_val("output_dir", self.temp_dir)
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("sr", 22050)
        bb.set_val("y", np.zeros(22050))
        bb.set_val("extracted_stems", {})

        node = SynthesizeFullAutoBackingNode()
        status = node.run(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        extracted = bb.get_val("extracted_stems", {})
        self.assertIn("backing", extracted)
        self.assertIn("backing_with_click", extracted)
        self.assertTrue(os.path.exists(extracted["backing"]))
        self.assertTrue(os.path.exists(extracted["backing_with_click"]))

    def test_full_auto_bt_engine_includes_backing(self):
        """驗證 FullAutoDemixingBTEngine run_full_auto_demixing 傳回字典包含 backing 與 backing_with_click」"""
        engine = FullAutoDemixingBTEngine()
        stems = engine.run_full_auto_demixing(self.audio_path, output_dir=self.temp_dir)
        self.assertIn("backing", stems)
        self.assertIn("backing_with_click", stems)
        self.assertTrue(os.path.exists(stems["backing_with_click"]))


if __name__ == "__main__":
    unittest.main()
