"""
SDD Pass 48 — 專項模型輸入前處理適配器 (StemInputGuardAdapter) 與推理快取測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.separator import StemInputGuardAdapter, CascadedStemSeparator


class TestSDDPass48SpecializedStemAdapter(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mono_wav_path = os.path.join(self.test_dir, "test_mono_48k.wav")
        # 生成 48000Hz 1 秒的 Mono WAV，音量高 (Peak = 1.0)
        sr = 48000
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.99).astype(np.float32)
        sf.write(self.mono_wav_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_input_guard_adapter_standardize_resampling_and_stereo(self):
        """驗證 StemInputGuardAdapter: 48k -> 44.1k, Mono -> Stereo, Peak Safeguard <= -1.0 dBFS"""
        out_path = os.path.join(self.test_dir, "standardized.wav")
        result_path = StemInputGuardAdapter.standardize_audio_input(
            self.mono_wav_path,
            output_path=out_path,
            target_sr=44100,
            require_stereo=True,
            max_peak_db=-1.0
        )
        self.assertTrue(os.path.exists(result_path))

        y, sr = sf.read(result_path)
        # 1. 採樣率應為 44100 Hz
        self.assertEqual(sr, 44100)
        # 2. 應為 2 聲道 Stereo
        self.assertEqual(y.ndim, 2)
        self.assertEqual(y.shape[1], 2)
        # 3. Peak 應小於等於 -1.0 dBFS (~0.89125)
        max_peak = np.max(np.abs(y))
        expected_max_peak = 10.0 ** (-1.0 / 20.0)
        self.assertLessEqual(max_peak, expected_max_peak + 1e-3)

    def test_input_guard_adapter_prerequisite_general_audio(self):
        """驗證 general_audio 前置條件不改變輸入音訊」"""
        res = StemInputGuardAdapter.prepare_prerequisite_audio(
            self.mono_wav_path, "general_audio", self.test_dir
        )
        self.assertEqual(res, self.mono_wav_path)

    def test_inference_cache_guard_reuse(self):
        """驗證 CascadedStemSeparator 快取在第二次調用時瞬間命中複用"""
        separator = CascadedStemSeparator()
        # 第一次模擬 Demucs 調用
        output_sub = os.path.join(self.test_dir, "stems")
        os.makedirs(output_sub, exist_ok=True)

        # 模擬快取寫入
        dummy_vocals = os.path.join(output_sub, "vocals.wav")
        dummy_drums = os.path.join(output_sub, "drums.wav")
        sf.write(dummy_vocals, np.zeros((44100, 2)), 44100)
        sf.write(dummy_drums, np.zeros((44100, 2)), 44100)

        cache_key = (os.path.abspath(self.mono_wav_path),
                     os.path.getsize(self.mono_wav_path),
                     "test_model",
                     output_sub)
        separator._demucs_cache[cache_key] = {"vocals": dummy_vocals, "drums": dummy_drums}

        # 再次調用應觸發 [Demucs Cache Guard]
        res = separator._demucs_separate(self.mono_wav_path, output_sub, "test_model", {"vocals"})
        self.assertIn("vocals", res)
        self.assertEqual(res["vocals"], dummy_vocals)

    def test_specialized_guitar_separation_runs(self):
        """驗證吉他分離介面能搭配 StemInputGuardAdapter 正確執行降級與適配」"""
        separator = CascadedStemSeparator()
        # 使用 1 秒音訊調用
        output_sub = os.path.join(self.test_dir, "guitar_stems")
        g_path, no_g_path = separator.separate_guitar(self.mono_wav_path, output_sub, is_already_instrumental=True)

        self.assertTrue(os.path.exists(g_path))
        self.assertTrue(os.path.exists(no_g_path))


if __name__ == "__main__":
    unittest.main()
