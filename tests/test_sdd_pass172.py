"""
SDD Pass 172 — Stage 3 BeatNet 決定性驗證：比對邏輯單元測試

背景：
scratch/pass172_beatnet_determinism_check.py 對黃金專案的節奏骨幹軌
(stems/submix/track_a_rhythm.wav) 實際跑了兩次 BeatNet DBN 推論，證實在
enable_deterministic_mode() 啟用下兩次都精確跑出 485 拍、時間戳誤差 0.0 秒
——推翻「黃金版拍數不可複現」的假設，把落差來源導向 Demucs 分軌本身的決定性
（見 docs/PASS-172-STAGE3-BEATNET-DETERMINISM-VERIFICATION-TASK.md）。

真正跑 BeatNet 需要 GPU 與模型權重，不適合放進 pytest。這裡只測試
pgm_craft.determinism.compare_beat_outputs() 這個比對邏輯本身：用合成的
beat 陣列驗證三種判定（完全一致 / 拍數一致但時間戳有微差 / 拍數不一致）。
"""

import pytest

from pgm_craft.determinism import compare_beat_outputs


class TestSDDPass172CompareBeatOutputs:

    def test_identical_outputs_are_deterministic(self):
        beats = [[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]
        result = compare_beat_outputs(beats, beats)

        assert result["count_match"] is True
        assert result["max_delta_sec"] == 0.0
        assert result["verdict"] == "DETERMINISTIC"

    def test_same_count_but_shifted_timestamps_is_mostly_deterministic(self):
        beats1 = [[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]
        beats2 = [[0.0, 1], [0.5021, 2], [1.0, 3], [1.5, 4]]
        result = compare_beat_outputs(beats1, beats2)

        assert result["count_match"] is True
        assert result["verdict"] == "MOSTLY_DETERMINISTIC"
        assert result["max_delta_sec"] == pytest.approx(0.0021)

    def test_different_beat_counts_is_non_deterministic(self):
        beats1 = [[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]
        beats2 = [[0.0, 1], [0.5, 2], [1.0, 3]]
        result = compare_beat_outputs(beats1, beats2)

        assert result["count_match"] is False
        assert result["max_delta_sec"] is None
        assert result["verdict"] == "NON_DETERMINISTIC"
        assert result["count1"] == 4
        assert result["count2"] == 3
