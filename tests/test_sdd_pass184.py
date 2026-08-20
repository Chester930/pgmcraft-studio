"""
SDD Pass 184 — SteadyPercussionCountAnchorNode 局部 onset 偵測 + 接受拍距整數倍

背景：
Pass 183 累積修復（Pass 180-183）真實資料回歸後，使用者實際試聽《World is
Mine》回報兩個問題：
1. 18-20 秒重音位置不對——`_detect_onsets` 對整首歌一次做 onset 偵測，
   安靜段落被後面響亮段落稀釋掉敏感度，原本驗證過的乾淨 hi-hat 五連拍
   找不全。
2. 0-3 秒 hi-hat 沒對到——查證後是隔拍打（half-time groove），底層拍速
   跟主歌一致，使用者確認前奏聽起來速度只有主歌一半、但這是鼓點稀疏造成
   的感覺，不是核心速度偵測錯誤。

詳見 docs/PASS-184-STEADY-PERCUSSION-LOCAL-ONSET-AND-HALFTIME-TASK.md。

本測試驗證：
1. 修法 A：對整首歌做 onset 偵測時，安靜段落夾在響亮段落之間也能被抓到
   （不會被稀釋），改成滑動視窗分段分析後能正確找到。
2. 修法 B：間隔等於拍距 2 倍的連續段（half-time），能被正確辨識、套用，
   且中間跳過的格點也被正確標成連貫的 1-2-3-4 循環。
3. 真實資料回歸：這次真實跑法查到的 0-3 秒案例（0.755s/1.486s/2.218s/
   2.949s，間隔約 0.731s ≈ 2×拍距）當固定資料，驗證正確辨識、正確套用。
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


class TestSDDPass184LocalOnsetDetection:

    def test_quiet_run_between_loud_sections_is_found_with_windowed_detection(self, tmp_path):
        """安靜段落夾在響亮段落之間，全曲一次分析容易被稀釋掉，改成滑動
        視窗分段分析後應該能正確找到。"""
        duration = 60.0
        quiet_times = [20.0, 20.36, 20.72, 21.08, 21.44]
        # 前後各放一段響亮、密集的噪聲，模擬副歌等響亮段落
        loud_times_before = list(np.arange(2.0, 15.0, 0.08))
        loud_times_after = list(np.arange(30.0, 45.0, 0.08))

        y = _click_train(quiet_times, duration, amp=0.15)  # 安靜段落振幅較低
        y += _click_train(loud_times_before, duration, amp=0.9)
        y += _click_train(loud_times_after, duration, amp=0.9)

        path = tmp_path / "hihat_cymbals.wav"
        sf.write(str(path), y, SR)

        node = SteadyPercussionCountAnchorNode()
        onsets = node._detect_onsets(str(path))
        found_quiet = [o for o in onsets if 19.5 <= o <= 21.8]
        assert len(found_quiet) >= 4

    def test_half_time_run_anchors_with_correctly_labeled_intermediate_beats(self, tmp_path):
        """間隔等於拍距 2 倍的連續段（half-time），應該被正確辨識、套用，
        且中間跳過的格點也要被正確標成連貫的 1-2-3-4 循環。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]

        # 隔拍：只在偶數格點打（間隔約 2×拍距）
        half_time_indexes = [10, 12, 14, 16]
        run_times = grid_times[half_time_indexes]
        kick_y = _click_train(run_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "ANCHORED"
        assert report["applied"][0]["stem"] == "kick"

        new_beats = bb.get_val("beats")
        labels = new_beats[:, 1].astype(int)
        # 從第一個快照點（index 10）開始，包含中間跳過的格點（11, 13, 15），
        # 都要是連貫的 1-2-3-4 循環。
        assert list(labels[10:18]) == [1, 2, 3, 4, 1, 2, 3, 4]

    def test_real_captured_halftime_intro_scenario(self, tmp_path):
        """回歸測試：節錄這次真實抓到的 0-3 秒案例（隔拍 hi-hat，間隔約
        0.731s ≈ 2×拍距 0.364s），驗證正確辨識、正確套用。"""
        duration = 12.0
        beat_sec = 0.364
        beats = _beats_grid(duration, beat_sec=beat_sec)

        real_onsets = [0.755, 1.486, 2.218, 2.949]
        hihat_y = _click_train(real_onsets, duration, freq=1200.0, decay=80.0)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "hihat_cymbals.wav"), hihat_y, SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "ANCHORED"
        assert report["applied"][0]["stem"] == "hihat_cymbals"

        new_beats = bb.get_val("beats")
        timestamps = new_beats[:, 0]

        def _label_near(t):
            idx = int(np.argmin(np.abs(timestamps - t)))
            return int(new_beats[idx, 1])

        # 隔拍型態每個擊點在格點上跳 2 步，標號依「格點位置」循環，所以是
        # 1,3,1,3（不是 1,2,3,4）——中間被跳過的格點（2,4 拍）才會補上。
        expected = [1, 3, 1, 3]
        for onset_t, exp_label in zip(real_onsets, expected):
            assert _label_near(onset_t) == exp_label
