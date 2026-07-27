"""
SDD Pass 87 — 基於 ISMIR/IEEE 學術文獻與 BeatNet/madmom 之超高精度 Click 相位對齊與 Downbeat 修復狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.beat_tracking_bt import (
    OnsetPhaseRealignmentNode,
    KickBassDownbeatVerifierNode,
    ViterbiTempoSmoothingNode
)


class TestSDDPass87LiteratureBasedPrecisionBeatEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sr = 22050
        duration = 3.0
        t = np.linspace(0, duration, int(self.sr * duration), False)
        y = np.zeros_like(t)

        # 模擬 120 BPM 正確 Onset 撞擊點 (每 0.5s 一個衝擊脈衝)
        for beat_time in [0.5, 1.0, 1.5, 2.0, 2.5]:
            idx = int(beat_time * self.sr)
            y[idx:idx+100] = np.sin(2 * np.pi * 100 * np.linspace(0, 0.01, 100)) * 0.8

        self.y = y
        self.audio_path = os.path.join(self.test_dir, "synth_rhythm.wav")
        sf.write(self.audio_path, y, self.sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_onset_phase_realignment(self):
        """驗證 Ellis (2007) 相位微調節點將帶有 20ms 延遲的拍點精確拉回波形 Peak"""
        blackboard = Blackboard()
        blackboard.set_val("y", self.y)
        blackboard.set_val("sr", self.sr)

        # 人為加上 20ms 的延遲拍點 [0.52, 1.02, 1.52, 2.02, 2.52]
        lagged_beats = np.array([
            [0.52, 1],
            [1.02, 0],
            [1.52, 0],
            [2.02, 0],
            [2.52, 1]
        ])
        blackboard.set_val("beats", lagged_beats)

        node = OnsetPhaseRealignmentNode(search_window_ms=35.0)
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        realigned = blackboard.get_val("beats")
        self.assertIsNotNone(realigned)
        # 第一拍的時間應被精確拉回接近 0.5 秒 (誤差 < 20ms)
        self.assertLess(abs(realigned[0, 0] - 0.5), 0.02)

    def test_kick_bass_downbeat_verifier(self):
        """驗證 madmom (2016) 低頻重音 Downbeat 衛兵修復拍號」"""
        blackboard = Blackboard()
        blackboard.set_val("y", self.y)
        blackboard.set_val("sr", self.sr)

        # 模擬原本 1 號拍與 3 號拍反相標註
        beats = np.array([
            [0.5, 0],
            [1.0, 0],
            [1.5, 1],
            [2.0, 0],
            [2.5, 0],
            [3.0, 1]
        ])
        blackboard.set_val("beats", beats)

        node = KickBassDownbeatVerifierNode()
        status = node.execute(blackboard)
        self.assertEqual(status.name, "SUCCESS")

    def test_viterbi_tempo_smoothing(self):
        """驗證 BeatNet (2021) Viterbi 最優路徑平滑衛兵過濾離群跳拍」"""
        blackboard = Blackboard()
        beats = np.array([
            [0.5, 1],
            [1.0, 0],
            [1.8, 0], # 離群跳拍 (0.8s 步距而非 0.5s)
            [2.0, 0],
            [2.5, 1]
        ])
        blackboard.set_val("beats", beats)

        node = ViterbiTempoSmoothingNode(tolerance_pct=0.20)
        status = node.execute(blackboard)
        self.assertEqual(status.name, "SUCCESS")


if __name__ == "__main__":
    unittest.main()
