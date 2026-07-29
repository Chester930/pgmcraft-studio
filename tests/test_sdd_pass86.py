"""
SDD Pass 86 — 純音樂伴奏 + Click 導出檔 (backing_with_click.wav) 單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.export_bt import BackingWithClickSynthesizerNode


class TestSDDPass86BackingWithClickSynthesizer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "test_audio.wav")
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_backing_with_click_synthesis(self):
        """驗證 BackingWithClickSynthesizerNode 成功導出 backing_with_click.wav」"""
        blackboard = Blackboard()
        y, sr = sf.read(self.audio_path)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)
        blackboard.set_val("output_dir", self.test_dir)
        blackboard.set_val("click_audio", y * 0.8)
        blackboard.set_val("stems", {"drums": y * 0.3, "bass": y * 0.3, "other": y * 0.3})

        node = BackingWithClickSynthesizerNode()
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out_p = blackboard.get_val("backing_with_click_path")
        self.assertIsNotNone(out_p)
        self.assertTrue(os.path.exists(out_p))

    def test_backing_with_click_preserves_backing_duration_when_click_sr_differs(self):
        """伴奏與 click 取樣率不同時，輸出長度應跟伴奏音檔一致，不可變成一半。"""
        backing_sr = 22050
        click_sr = 44100
        duration_sec = 2.0
        backing_path = os.path.join(self.test_dir, "no_vocals.wav")
        click_path = os.path.join(self.test_dir, "click_track.wav")

        t_backing = np.linspace(0, duration_sec, int(backing_sr * duration_sec), False)
        backing = (np.sin(2 * np.pi * 220 * t_backing) * 0.25).astype(np.float32)
        sf.write(backing_path, backing, backing_sr)

        t_click = np.linspace(0, duration_sec, int(click_sr * duration_sec), False)
        click = np.zeros_like(t_click, dtype=np.float32)
        click[::click_sr // 2] = 0.5
        sf.write(click_path, click, click_sr)

        blackboard = Blackboard()
        blackboard.set_val("sr", click_sr)
        blackboard.set_val("output_dir", self.test_dir)
        blackboard.set_val("click_track", click_path)
        blackboard.set_val("stems", {"no_vocals": backing_path})

        status = BackingWithClickSynthesizerNode().execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out_p = blackboard.get_val("backing_with_click_path")
        out, out_sr = sf.read(out_p)
        self.assertEqual(out_sr, backing_sr)
        self.assertAlmostEqual(len(out) / out_sr, duration_sec, places=2)
        self.assertEqual(blackboard.get_val("backing_with_click_sample_rate"), backing_sr)

    def test_backing_with_click_accepts_channel_first_stem_arrays(self):
        """分軌模型常回傳 channels x samples，轉 mono 時不可把音檔壓成 2 個 samples。"""
        sr = 22050
        duration_sec = 1.0
        samples = int(sr * duration_sec)
        stereo_channel_first = np.vstack([
            np.ones(samples, dtype=np.float32) * 0.1,
            np.ones(samples, dtype=np.float32) * 0.2,
        ])

        blackboard = Blackboard()
        blackboard.set_val("sr", sr)
        blackboard.set_val("output_dir", self.test_dir)
        blackboard.set_val("click_audio", np.zeros(samples, dtype=np.float32))
        blackboard.set_val("stems", {"no_vocals": stereo_channel_first})

        status = BackingWithClickSynthesizerNode().execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out, out_sr = sf.read(blackboard.get_val("backing_with_click_path"))
        self.assertEqual(out_sr, sr)
        self.assertAlmostEqual(len(out) / out_sr, duration_sec, places=2)


if __name__ == "__main__":
    unittest.main()
