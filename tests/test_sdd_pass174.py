"""
SDD Pass 174 — 修復 Demucs 分軌決定性（reseed_for_inference）單元測試

背景：
Pass 173 證實 CascadedStemSeparator._demucs_separate() 呼叫 apply_model() 時吃
demucs 套件預設的 shifts=1（隨機時間平移 test-time augmentation），
enable_deterministic_mode() 只在 pipeline 啟動時 seed 一次、沒有覆蓋到這個呼叫點
自己消耗的隨機性，導致同一份輸入音訊每次重新分離都不是同一份（max_abs_diff=0.234）。

Pass 174 在 _demucs_separate() 呼叫 apply_model() 前加了
pgm_craft.determinism.reseed_for_inference()。這裡測試該函式本身的行為：
呼叫後 random / numpy 的下一次抽樣，在兩次獨立呼叫之間必須完全一致。
真正驗證它修好了 Demucs（而不是這個 reseed 函式本身），走的是
scratch/pass174_demucs_reseed_fix_verification.py 的真實模型驗證
（見 docs/PASS-174-DEMUCS-RESEED-DETERMINISM-FIX-TASK.md）。
"""

import random

import numpy as np

from pgm_craft.determinism import enable_deterministic_mode, reseed_for_inference


class TestSDDPass174ReseedForInference:

    def test_reseed_makes_random_module_draw_reproducible(self):
        reseed_for_inference(seed=123)
        draw1 = random.random()

        reseed_for_inference(seed=123)
        draw2 = random.random()

        assert draw1 == draw2

    def test_reseed_makes_numpy_draw_reproducible(self):
        reseed_for_inference(seed=123)
        draw1 = np.random.rand(4)

        reseed_for_inference(seed=123)
        draw2 = np.random.rand(4)

        assert np.array_equal(draw1, draw2)

    def test_reseed_without_explicit_seed_falls_back_to_last_enabled_seed(self):
        enable_deterministic_mode(seed=99)

        reseed_for_inference()
        draw1 = random.random()

        reseed_for_inference()
        draw2 = random.random()

        assert draw1 == draw2

        # restore the module default so other tests in the same session aren't affected
        enable_deterministic_mode(seed=42)

    def test_different_seeds_draw_different_values(self):
        reseed_for_inference(seed=1)
        draw1 = random.random()

        reseed_for_inference(seed=2)
        draw2 = random.random()

        assert draw1 != draw2
