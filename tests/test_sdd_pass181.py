"""
SDD Pass 181 — SteadyPercussionCountAnchorNode 連續穩定擊點當第一拍續接錨點

背景：
使用者聽過 Pass 180 修好的版本後回報《World is Mine》前奏/間奏有「第一拍
沒對上」的問題，並提出構想：連續四個等間隔擊點代表打擊樂器在明確數 1234
拍，可以當拍號續接依據。真實資料驗證發現這個訊號不只 kick 會有——真正乾淨
的案例是打在 hi-hat 上（18.561s-20.012s，變異係數 2.6%，間隔幾乎完全等於
全曲拍距），且必須用真正的 onset 偵測（不是窗口最大值包絡）才抓得到，詳見
docs/PASS-181-STEADY-PERCUSSION-COUNT-DOWNBEAT-ANCHOR-TASK.md。

本測試驗證：
1. 真的連續等間隔、間隔貼近全曲拍距的擊點段，會被正確辨識、標記成 1234，
   並往後續接循環。
2. 間隔規律但跟全曲拍距差很多（例如 2.5 倍）的段落，不會被誤判。
3. 過門式密集擊點（間隔遠短於拍距）不會被誤判。
4. 沒有任何樂器音軌時安全空操作。
5. 用這次真實抓到的案例（hi-hat 18.561s-20.012s）當回歸固定資料，驗證能
   正確辨識並套用。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus

SR = 22050
BEAT_SEC = 0.36  # 對應約 166 BPM，跟《World is Mine》實測拍距一致


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
    """全曲時間格點都對（拍距正確），但標記統一給一個錯誤的固定拍號——
    模擬「節拍還可以接受，但第一拍沒對上」的真實情境。"""
    times = np.arange(0.0, duration_sec, beat_sec)
    return np.array([[t, wrong_label] for t in times])


class TestSDDPass181SteadyPercussionCountAnchor:

    def test_clean_steady_run_anchors_and_continues_cycle(self, tmp_path):
        duration = 12.0
        beats = _beats_grid(duration)

        # 找出第 10-13 個格點的時間，當作 kick 連續四拍
        grid_times = beats[:, 0]
        run_times = grid_times[10:14]
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
        # 錨點本身標記成 1,2,3,4
        assert list(labels[10:14]) == [1, 2, 3, 4]
        # 往後續接循環
        assert list(labels[14:18]) == [1, 2, 3, 4]

    def test_regular_but_wrong_scale_interval_not_anchored(self, tmp_path):
        duration = 12.0
        beats = _beats_grid(duration)

        # 間隔規律（變異係數低）但長度是全曲拍距的 2.5 倍，不該被當成逐拍
        run_times = [3.0, 3.0 + BEAT_SEC * 2.5, 3.0 + BEAT_SEC * 5.0, 3.0 + BEAT_SEC * 7.5]
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
        assert report["status"] == "NO_STEADY_RUN_FOUND"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)

    def test_dense_fill_not_anchored(self, tmp_path):
        duration = 12.0
        beats = _beats_grid(duration)

        # 過門式密集擊點：間隔遠短於全曲拍距（16 分音符等級）
        fill_start = 5.0
        run_times = [fill_start + i * (BEAT_SEC / 4.0) for i in range(6)]
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
        assert report["status"] == "NO_STEADY_RUN_FOUND"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)

    def test_no_stems_is_safe_noop(self, tmp_path):
        duration = 8.0
        beats = _beats_grid(duration)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))  # 目錄存在但沒有任何音軌檔案

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "NO_STEADY_RUN_FOUND"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)

    def test_real_captured_hihat_scenario_anchors_correctly(self, tmp_path):
        """回歸測試：節錄這次真實抓到的案例——hi-hat 在 18.561s-20.012s 連續
        四個間隔（0.372/0.360/0.348/0.372s），變異係數 2.6%，幾乎完全等於
        全曲拍距 0.364s。"""
        duration = 24.0
        beat_sec = 0.364
        beats = _beats_grid(duration, beat_sec=beat_sec)

        real_hihat_onsets = [18.561, 18.933, 19.293, 19.641, 20.012]
        hihat_y = _click_train(real_hihat_onsets, duration, freq=1200.0, decay=80.0)

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
        assert report["applied"][0]["count"] == 5

        new_beats = bb.get_val("beats")
        timestamps = new_beats[:, 0]

        def _label_near(t):
            idx = int(np.argmin(np.abs(timestamps - t)))
            return int(new_beats[idx, 1]), idx

        # 五個真實 onset 對應到的拍點，應該被標記成連貫的 1,2,3,4,1
        expected = [1, 2, 3, 4, 1]
        snapped_indexes = []
        for onset_t, exp_label in zip(real_hihat_onsets, expected):
            label, idx = _label_near(onset_t)
            assert label == exp_label
            snapped_indexes.append(idx)
        # 快照點彼此應該是連續的格點索引（間隔真的貼合全曲拍距）
        assert snapped_indexes == list(range(snapped_indexes[0], snapped_indexes[0] + 5))

        # 錨點之後應該繼續往後續接 1234 循環
        last_idx = snapped_indexes[-1]
        following_labels = [int(new_beats[last_idx + step, 1]) for step in range(1, 5)]
        assert following_labels == [2, 3, 4, 1]
