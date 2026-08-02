"""
SDD Pass 155 — 決定性推論模式，讓 BeatNet/Demucs 結果可重現

背景：連續三次同一首歌、同一份程式碼的真實測試，v1 的 commercial_beat_quality
分數在 88.71 / 88.47 / 89.3 之間飄動——v1 的演算法本身完全沒有被改動過，這個
飄動只能來自模型推論本身的執行間隨機性。追查發現整個專案從未固定過任何隨機
種子，而且 BeatNet／Demucs 都是在 GPU 上跑神經網路推論，PyTorch 預設情況下
cuDNN 會對同一層卷積嘗試多種演算法、挑當下跑起來最快的那個（autotune），這個
挑選過程本身受硬體當下狀態影響，導致同一份權重、同一份輸入音檔，不同次執行
可能產生些微不同的輸出——這讓我們沒辦法區分「程式碼改動真的有效」還是「這次
運氣好」。

新增 pgm_craft/determinism.py 的 enable_deterministic_mode()：固定
random/numpy/torch 種子、關閉 cuDNN 自動調校（benchmark=False）、開啟
cudnn.deterministic 與 torch.use_deterministic_algorithms（warn_only=True，
極少數沒有決定性 GPU 實作的運算子會降級為警告而非直接崩潰）、並在任何 CUDA
context 建立前設定 CUBLAS_WORKSPACE_CONFIG 環境變數（PyTorch 官方文件要求，
確定性 cuBLAS matmul 運算的必要條件）。

接進 PGMCraftEngine.__init__()——這是「一鍵生成」「節奏定位」等所有真實入口點
唯一共同會經過的地方，且在任何 BT 節點執行之前（這個專案的 torch/BeatNet/
Demucs import 都是延遲到節點 execute() 內部才發生，所以在這裡呼叫來得及）。
新增 deterministic 參數（預設 True），可關閉以換取速度。

本測試驗證：
A. enable_deterministic_mode() 本身：正確設定各項旗標、環境變數；重複呼叫是
   冪等的；沒有 torch/GPU 的環境下也能安全執行不出錯。
B. PGMCraftEngine 建構子正確呼叫、可透過 deterministic=False 關閉、向後相容
   （所有既有呼叫端都用關鍵字參數，不受新參數影響）。
C. 端對端真實驗證（機器上有 GPU 時才跑）：用 sample_test.wav 分別跑兩次完全
   獨立的 Demucs 分軌與 BeatNet 節拍追蹤（用不同輸出資料夾繞過分軌快取），
   確認兩次結果逐位元完全一致。
"""

import os

import numpy as np
import pytest

from pgm_craft.determinism import enable_deterministic_mode, is_deterministic_mode_enabled
from pgm_craft.pipeline import PGMCraftEngine


class TestEnableDeterministicMode:

    def test_applies_expected_settings(self):
        report = enable_deterministic_mode(seed=123)
        assert report["status"] == "ENABLED"
        assert report["seed"] == 123
        assert "random.seed" in report["applied"]
        assert "CUBLAS_WORKSPACE_CONFIG" in report["applied"]

    def test_sets_cublas_workspace_config_env_var(self):
        os.environ.pop("CUBLAS_WORKSPACE_CONFIG", None)
        enable_deterministic_mode()
        assert os.environ.get("CUBLAS_WORKSPACE_CONFIG") == ":4096:8"

    def test_idempotent_when_called_twice(self):
        report1 = enable_deterministic_mode(seed=7)
        report2 = enable_deterministic_mode(seed=7)
        assert report1["applied"] == report2["applied"]

    def test_marks_module_state_enabled(self):
        enable_deterministic_mode()
        assert is_deterministic_mode_enabled() is True

    def test_random_seed_actually_reproducible(self):
        import random

        enable_deterministic_mode(seed=99)
        first = [random.random() for _ in range(5)]
        enable_deterministic_mode(seed=99)
        second = [random.random() for _ in range(5)]
        assert first == second

    def test_numpy_seed_actually_reproducible(self):
        enable_deterministic_mode(seed=99)
        first = np.random.rand(5).tolist()
        enable_deterministic_mode(seed=99)
        second = np.random.rand(5).tolist()
        assert first == second


class TestPGMCraftEngineWiring:

    def test_deterministic_enabled_by_default(self):
        engine = PGMCraftEngine(enable_stem_separation=False)
        assert engine.determinism_report["status"] == "ENABLED"

    def test_deterministic_can_be_disabled(self):
        engine = PGMCraftEngine(enable_stem_separation=False, deterministic=False)
        assert engine.determinism_report["status"] == "DISABLED"

    def test_existing_call_sites_still_work_without_new_kwarg(self):
        """All real call sites (app.py, cli.py, main.py) use keyword args and
        never pass `deterministic` explicitly -- confirm the new parameter's
        default doesn't break them."""
        engine = PGMCraftEngine(enable_stem_separation=False, validate_contracts=True)
        assert engine.determinism_report["status"] == "ENABLED"
        assert engine.validate_contracts is True


def _torch_cuda_available():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


@pytest.mark.skipif(not _torch_cuda_available(), reason="determinism verification requires a CUDA GPU")
class TestRealInferenceReproducibility:

    def test_demucs_bit_identical_across_independent_runs(self, tmp_path):
        from pgm_craft.separator import CascadedStemSeparator

        audio = os.path.abspath("sample_test.wav")
        out_a = str(tmp_path / "a")
        out_b = str(tmp_path / "b")
        os.makedirs(out_a, exist_ok=True)
        os.makedirs(out_b, exist_ok=True)

        enable_deterministic_mode()
        paths_a = CascadedStemSeparator()._demucs_separate(audio, out_a, "htdemucs_ft", {"drums", "bass"})
        enable_deterministic_mode()
        paths_b = CascadedStemSeparator()._demucs_separate(audio, out_b, "htdemucs_ft", {"drums", "bass"})

        import soundfile as sf
        for name in paths_a:
            ya, _ = sf.read(paths_a[name])
            yb, _ = sf.read(paths_b[name])
            assert np.array_equal(ya, yb), f"{name} differed between independent runs"

    def test_beatnet_bit_identical_across_independent_runs(self):
        from BeatNet.BeatNet import BeatNet

        audio = os.path.abspath("sample_test.wav")

        enable_deterministic_mode()
        output1 = np.asarray(BeatNet(1, mode="offline", inference_model="DBN", plot=[], thread=False).process(audio))
        enable_deterministic_mode()
        output2 = np.asarray(BeatNet(1, mode="offline", inference_model="DBN", plot=[], thread=False).process(audio))

        assert output1.shape == output2.shape
        assert np.array_equal(output1, output2)
