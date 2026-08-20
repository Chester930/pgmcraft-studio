"""
SDD Pass 186 — SteadyPercussionCountAnchorNode 整軌確認允許少量擊點不匹配

背景：
Pass 185 驗證時發現，18-20 秒的重音位置仍然沒有修正——追查後確認不是
Pass 185 保護機制失效，而是候選在更早階段就被 Pass 182 的「整軌能量確認」
機制拒絕掉了。真實資料查證：《World is Mine》18.563s-20.014s 的 hi-hat
五連拍，五個擊點裡有四個跟整軌偵測結果完全對上（誤差 0.000 秒），只有一個
（18.934s）整軌沒有對應能量——「全有全無」的判斷把這種大多數乾淨對應、
只有少數沒抓到獨立峰值的真實案例也一起拒絕掉了。詳見
docs/PASS-186-WHOLE-TRACK-CONFIRM-TOLERATE-ONE-MISS-TASK.md。

本測試驗證：
1. 全部擊點都對上整軌時，維持既有行為（正常通過）。
2. 只有 1 個擊點沒對上整軌時，這次改成允許通過（新行為）。
3. 2 個以上擊點沒對上整軌時，依然拒絕（沒有因為放寬就完全不設限）。
4. 真實資料回歸：節錄真實案例的整軌/細分軌 onset 時間資料，驗證正確通過。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus

SR = 22050
BEAT_SEC = 0.36


def _click_train(times, duration_sec, sr=SR, freq=200.0, decay=40.0, amp=0.9):
    n = int(duration_sec * sr)
    y = np.zeros(n)
    click_len = int(0.05 * sr)
    t_click = np.linspace(0, 0.05, click_len, endpoint=False)
    click = amp * np.sin(2 * np.pi * freq * t_click) * np.exp(-t_click * decay)
    for t in times:
        idx = int(t * sr)
        end = min(n, idx + click_len)
        actual = end - idx
        if actual > 0 and idx < n:
            y[idx:end] += click[:actual]
    return y


def _beats_grid(duration_sec, beat_sec=BEAT_SEC, wrong_label=2):
    times = np.arange(0.0, duration_sec, beat_sec)
    return np.array([[t, wrong_label] for t in times])


class TestSDDPass186WholeTrackConfirmToleratesOneMiss:

    def test_all_onsets_confirmed_still_anchors(self, tmp_path):
        """全部擊點都對上整軌時，維持既有行為，正常通過。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]
        run_times = grid_times[10:14]
        kick_y = _click_train(run_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        sf.write(str(drums_dir / "drums.wav"), kick_y, SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "ANCHORED"
        assert report["rejected"] == []

    def test_one_unconfirmed_onset_now_anchors(self, tmp_path):
        """新行為：5 個擊點裡只有 1 個整軌沒有對應能量，這次應該通過。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]
        run_times = grid_times[10:15]  # 5 個擊點
        kick_y = _click_train(run_times, duration)

        # 整軌只在前 4 個時間點有能量，第 5 個（run_times[4]）故意留空
        whole_track_times = list(run_times[:4])
        whole_y = _click_train(whole_track_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        sf.write(str(drums_dir / "drums.wav"), whole_y, SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "ANCHORED"
        assert report["rejected"] == []
        assert report["applied"][0]["stem"] == "kick"

    def test_two_unconfirmed_onsets_still_rejected(self, tmp_path):
        """2 個以上擊點沒對上整軌時，依然拒絕，不能因為放寬就完全不設限。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]
        run_times = grid_times[10:15]
        kick_y = _click_train(run_times, duration)

        # 整軌只在前 3 個時間點有能量，後 2 個故意留空
        whole_track_times = list(run_times[:3])
        whole_y = _click_train(whole_track_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        sf.write(str(drums_dir / "drums.wav"), whole_y, SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] in ("NO_STEADY_RUN_FOUND", "CANDIDATES_FOUND_BUT_NOT_APPLIED")
        assert len(report["rejected"]) == 1
        assert report["rejected"][0]["reason"] == "REJECTED_NO_WHOLE_TRACK_ENERGY"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)

    def test_real_captured_scenario_now_confirmed(self, tmp_path):
        """回歸測試：節錄真實案例（《World is Mine》18.563s-20.014s hi-hat
        五連拍，五個裡四個跟整軌完全對上，1 個（18.934s）沒對上），驗證
        這次正確通過確認、正確套用。"""
        duration = 24.0
        beat_sec = 0.36463
        beats = _beats_grid(duration, beat_sec=beat_sec)

        real_hihat_onsets = [18.563, 18.934, 19.294, 19.642, 20.014]
        hihat_y = _click_train(real_hihat_onsets, duration, freq=1200.0, decay=80.0)

        # 整軌：四個對上（18.563/19.294/19.642/20.014），18.934 這個故意留空
        whole_track_onsets = [18.563, 19.294, 19.642, 20.014]
        whole_y = _click_train(whole_track_onsets, duration, freq=300.0, decay=30.0)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "hihat_cymbals.wav"), hihat_y, SR)
        sf.write(str(drums_dir / "drums.wav"), whole_y, SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "ANCHORED"
        assert report["rejected"] == []
        assert report["applied"][0]["stem"] == "hihat_cymbals"

        new_beats = bb.get_val("beats")
        timestamps = new_beats[:, 0]

        def _label_near(t):
            idx = int(np.argmin(np.abs(timestamps - t)))
            return int(new_beats[idx, 1])

        expected = [1, 2, 3, 4, 1]
        for onset_t, exp_label in zip(real_hihat_onsets, expected):
            assert _label_near(onset_t) == exp_label
