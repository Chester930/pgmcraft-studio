"""
SDD Pass 173 — Demucs 分軌決定性驗證：比對邏輯單元測試

背景：
scratch/pass173_demucs_determinism_check.py 對黃金專案的 denoised 來源音訊實際跑了
htdemucs_ft 兩次分離，證實 demucs 套件預設的 shifts=1（隨機時間平移 test-time
augmentation）讓連續兩次分離不是 bit-exact（最大絕對誤差 0.234），而 shifts=0
（關閉隨機平移）連續兩次分離完全 bit-exact（誤差 0.0）——這就是 Pass 171 量到的
「477 vs 黃金版 485 拍」落差的根本原因，見
docs/PASS-173-DEMUCS-STEM-SEPARATION-DETERMINISM-TASK.md。

真正跑 Demucs 需要 GPU 與模型權重，不適合放進 pytest。這裡只測試
pgm_craft.determinism.compare_audio_arrays() 這個比對邏輯本身。
"""

import numpy as np
import pytest

from pgm_craft.determinism import compare_audio_arrays


class TestSDDPass173CompareAudioArrays:

    def test_identical_arrays_are_bit_exact(self):
        arr = np.array([0.1, -0.2, 0.3, 0.0], dtype=np.float32)
        result = compare_audio_arrays(arr, arr.copy())

        assert result["bit_exact"] is True
        assert result["max_abs_diff"] == 0.0
        assert result["shape_mismatch"] is False

    def test_shifted_arrays_are_not_bit_exact(self):
        arr1 = np.array([0.1, -0.2, 0.3, 0.0], dtype=np.float32)
        arr2 = np.array([0.1, -0.2, 0.3, 0.234], dtype=np.float32)
        result = compare_audio_arrays(arr1, arr2)

        assert result["bit_exact"] is False
        assert result["max_abs_diff"] == pytest.approx(0.234, abs=1e-5)

    def test_shape_mismatch_is_reported_without_crashing(self):
        arr1 = np.zeros((2, 4))
        arr2 = np.zeros((2, 5))
        result = compare_audio_arrays(arr1, arr2)

        assert result["shape_mismatch"] is True
        assert result["bit_exact"] is False
        assert result["max_abs_diff"] is None
