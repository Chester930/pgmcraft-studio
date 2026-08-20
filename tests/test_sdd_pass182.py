"""
SDD Pass 182 — SteadyPercussionCountAnchorNode 補上整個鼓軌比對

背景：
Pass 181 做完後，使用者指出這個節點違反了原本的設計原則：「先從整個鼓軌
辨識，如果有不確定的部分，就透過鼓的細分軌來分析，進行比對與調整。」但
Pass 181 的節點一開始只看 kick/snare/hihat_cymbals 三個細分軌，完全沒有
回頭比對整個鼓軌（`drums.wav`）——分軌是 Demucs 頻段分離出來的，細分軌裡
看起來很乾淨的規律擊點，有可能是分離殘留的假訊號，真實混音裡根本沒有對應
的聲音。詳見 docs/PASS-182-WHOLE-DRUM-TRACK-CROSSCHECK-TASK.md。

本測試驗證：
1. 細分軌候選被整軌確認：Pass 181 原本會通過的案例，補上對應的整個鼓軌
   音檔後，依然正常通過、行為一致。
2. 細分軌候選被整軌拒絕（新增情境）：細分軌裡有乾淨規律擊點，但整個鼓軌
   在對應時間完全沒有能量（模擬分離殘留假訊號），驗證正確拒絕、且記錄
   `REJECTED_NO_WHOLE_TRACK_ENERGY`。
3. 整軌候選單獨成立：沒有單一細分軌能完整涵蓋的連續段，但整個鼓軌本身有
   （模擬兩個樂器輪流補位），驗證整軌自己的候選被正確找到並採用。
4. 真實資料回歸：《World is Mine》hi-hat 18.561s-20.012s 案例，補上對應的
   整個鼓軌音檔後依然正確辨識、正確採用。
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


class TestSDDPass182WholeDrumTrackCrosscheck:

    def test_confirmed_sub_run_still_anchors(self, tmp_path):
        """Pass 181 原本會通過的案例，補上對應的整個鼓軌音檔後依然正常通過。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]
        run_times = grid_times[10:14]
        kick_y = _click_train(run_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        # 整個鼓軌在同樣時間點也有對應能量（真實混音本來就有這個 kick）
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
        assert report["applied"][0]["stem"] == "kick"
        assert report["rejected"] == []

        new_beats = bb.get_val("beats")
        labels = new_beats[:, 1].astype(int)
        assert list(labels[10:14]) == [1, 2, 3, 4]

    def test_sub_run_rejected_without_whole_track_energy(self, tmp_path):
        """細分軌裡有乾淨規律擊點，但整個鼓軌在對應時間完全沒有能量
        （模擬分離殘留假訊號），應該被拒絕、不套用。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]
        run_times = grid_times[10:14]
        kick_y = _click_train(run_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)

        # 整個鼓軌在別的時間點有活動（不是完全空白的音軌），但在 kick 那段
        # 完全沒有對應能量——這是真正可疑的分離殘留假訊號情境。
        unrelated_times = [2.0, 2.36, 2.72, 3.08]
        drums_y = _click_train(unrelated_times, duration)
        sf.write(str(drums_dir / "drums.wav"), drums_y, SR)

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
        assert report["rejected"][0]["stem"] == "kick"
        assert report["rejected"][0]["reason"] == "REJECTED_NO_WHOLE_TRACK_ENERGY"

        # beats 不應該被動到
        np.testing.assert_array_equal(bb.get_val("beats"), beats)

    def test_whole_track_only_candidate_anchors(self, tmp_path):
        """沒有單一細分軌能完整涵蓋的連續段，但整個鼓軌本身有（模擬兩個
        樂器輪流補位打拍），應該被當作 source="drums" 的候選採用。"""
        duration = 12.0
        beats = _beats_grid(duration)
        grid_times = beats[:, 0]
        run_times = list(grid_times[10:14])

        # kick 只打第 1、3 個時間點，snare 只打第 2、4 個——各自都不足 4 個
        # 連續等間隔擊點，但整個鼓軌（兩者疊加）合起來有完整連續四拍。
        kick_only_times = [run_times[0], run_times[2]]
        snare_only_times = [run_times[1], run_times[3]]

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), _click_train(kick_only_times, duration), SR)
        sf.write(str(drums_dir / "snare.wav"), _click_train(snare_only_times, duration, freq=600.0), SR)
        sf.write(str(drums_dir / "drums.wav"), _click_train(run_times, duration), SR)

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("steady_percussion_anchor_report")
        assert report["status"] == "ANCHORED"
        assert report["applied"][0]["stem"] == "drums"

        new_beats = bb.get_val("beats")
        labels = new_beats[:, 1].astype(int)
        assert list(labels[10:14]) == [1, 2, 3, 4]

    def test_real_captured_hihat_scenario_still_anchors_with_whole_track(self, tmp_path):
        """回歸測試：hi-hat 18.561s-20.012s 真實案例，補上對應的整個鼓軌
        音檔後依然正確辨識、正確採用。"""
        duration = 24.0
        beat_sec = 0.364
        beats = _beats_grid(duration, beat_sec=beat_sec)

        real_hihat_onsets = [18.561, 18.933, 19.293, 19.641, 20.012]
        hihat_y = _click_train(real_hihat_onsets, duration, freq=1200.0, decay=80.0)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "hihat_cymbals.wav"), hihat_y, SR)
        # 真實查證過整個鼓組軌在這幾個時間點本來就有對應能量（見 Pass 181
        # 驗證過程紀錄），這裡合成同樣的能量存在。
        sf.write(str(drums_dir / "drums.wav"), hihat_y, SR)

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
        assert report["rejected"] == []

        new_beats = bb.get_val("beats")
        timestamps = new_beats[:, 0]

        def _label_near(t):
            idx = int(np.argmin(np.abs(timestamps - t)))
            return int(new_beats[idx, 1])

        expected = [1, 2, 3, 4, 1]
        for onset_t, exp_label in zip(real_hihat_onsets, expected):
            assert _label_near(onset_t) == exp_label
