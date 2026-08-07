"""
SDD Pass 180 — ViterbiTempoSmoothingNode 孤立離群值判斷邏輯治本修正

背景：
Pass 178 的 GapReinforcementNode 真實資料 A/B 回歸測試中，使用者實際試聽發現
處理組的 click track 出現數秒完全靜音。追查後確認：ViterbiTempoSmoothingNode
用「跟全曲單一中位數比較」判斷孤立離群值，完全沒有檢查「孤不孤立」——一整段
連續、內部彼此一致但跟全曲中位數不同的拍點（例如 GapReinforcementNode 補強
出的區塊），會被整串誤判成離群值，且修正值疊加在已修正過的時間點上造成連鎖
漂移，最終被壓縮/搬移到跟原始位置差很多的地方（見
docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md 第 4.3.1 節）。

修法：改用局部滾動中位數（前後各 window_beats 個拍距）判斷離群值，並且每個
離群點的修正值一律從原始未修改的陣列計算，不連鎖——這是
module3_barstart_v2_bt.BarStartTempoSmoothingNode（Pass 144）已經驗證過的
同一套原則。

本測試驗證：
1. 保留舊行為：真正孤立的單拍雜訊（前後鄰居都正常）仍然會被正確修正。
2. 修復新 bug：一整段連續、內部一致但跟全曲節奏不同的拍點區塊，不會再被
   整批誤判、壓縮消失。
3. 用這次真實抓到的案例（GapReinforcementNode 匯出的 21 個連續拍點）當回歸
   測試固定資料，驗證不再被壓縮進更短的時間窗。
"""

import numpy as np

from pgm_craft.workflow.beat_tracking_bt import ViterbiTempoSmoothingNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass180ViterbiIsolatedOutlierFix:

    def test_isolated_single_beat_glitch_still_corrected(self):
        """保留舊行為：0.5s 規律節奏中夾雜一個孤立的 0.8s 離群拍距，
        仍然要被正確修正回 0.5s（跟 Pass 87 既有測試的場景/期望值一致）。"""
        beats = np.array([
            [0.5, 1],
            [1.0, 0],
            [1.8, 0],  # 離群跳拍（0.8s 步距而非 0.5s）
            [2.3, 0],
            [2.8, 1],
            [3.3, 0],
        ])
        bb = Blackboard()
        bb.set_val("beats", beats)

        node = ViterbiTempoSmoothingNode(tolerance_pct=0.20)
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        smoothed = bb.get_val("beats")
        assert abs(smoothed[2, 0] - 1.5) < 1e-9
        report = bb.get_val("smoothing_report")
        assert report["outlier_count"] == 1

    def test_contiguous_different_tempo_block_not_compressed(self):
        """新行為：一整段連續 16 拍、節奏跟全曲中位數不同但內部彼此一致的區塊
        （模擬 GapReinforcementNode 補強出的缺口），不應該被整批誤判成離群值、
        壓縮進更短的時間窗——這正是 Pass 178 實測抓到的 bug。"""
        normal_step = 0.36  # 全曲主要節奏，約 166 BPM
        block_step = 0.72   # 補強區塊自己的節奏，跟全曲中位數差超過 20%

        times = [0.0]
        for _ in range(10):
            times.append(times[-1] + normal_step)
        block_start_index = len(times)
        for _ in range(16):
            times.append(times[-1] + block_step)
        block_end_index = len(times) - 1
        for _ in range(10):
            times.append(times[-1] + normal_step)

        beats = np.array([[t, (i % 4) + 1] for i, t in enumerate(times)])
        original_block_span = times[block_end_index] - times[block_start_index]

        bb = Blackboard()
        bb.set_val("beats", beats)
        node = ViterbiTempoSmoothingNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        smoothed = bb.get_val("beats")
        smoothed_block_span = smoothed[block_end_index, 0] - smoothed[block_start_index, 0]

        # 舊 bug 會把這段壓縮成大約一半長；治本後應該幾乎維持原本的跨度。
        assert smoothed_block_span > original_block_span * 0.9

        # 區塊內部彼此相鄰的拍點，不應該被搬移超過一個拍距。
        for i in range(block_start_index, block_end_index + 1):
            assert abs(smoothed[i, 0] - beats[i, 0]) < block_step

    def test_real_captured_gap_reinforcement_scenario_not_corrupted(self):
        """回歸測試：用這次真實抓到的案例（GapReinforcementNode 對《World is
        Mine》缺口補強後匯出的實際拍點資料，4.389s-18.947s 連續 21 拍）當固定
        資料，驗證修好後這段不再被壓縮進 2.6s-9.8s（實際觀測到的舊 bug 現象）。"""
        # 節錄自 reports/gap_reinforcement/beats.json 裡真實出現問題的區段：
        # 4.389s 起、間隔約 0.72-0.74s 的 21 個連續拍點（缺口補強區塊），前後
        # 接回全曲約 0.36s 間隔的正常節奏。
        block_times = [
            4.389571, 5.17805, 5.921088, 6.640907, 7.360726, 8.103764,
            8.777143, 9.473741, 10.17034, 10.890159, 11.726077, 12.422676,
            13.212154, 14.094512, 14.814331, 15.48771, 16.184308, 16.904127,
            17.600726, 18.297324, 18.947483,
        ]
        pre_times = [round(block_times[0] - 0.36 * (i + 1), 6) for i in range(6)][::-1]
        post_times = [round(block_times[-1] + 0.34 * (i + 1), 6) for i in range(6)]
        all_times = pre_times + block_times + post_times

        beats = np.array([[t, (i % 4) + 1] for i, t in enumerate(all_times)])
        block_start_index = len(pre_times)
        block_end_index = block_start_index + len(block_times) - 1

        bb = Blackboard()
        bb.set_val("beats", beats)
        node = ViterbiTempoSmoothingNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        smoothed = bb.get_val("beats")

        original_span = block_times[-1] - block_times[0]
        smoothed_span = smoothed[block_end_index, 0] - smoothed[block_start_index, 0]
        # 舊 bug：14.56 秒被壓縮成約 7.2 秒。治本後應該維持接近原本跨度。
        assert smoothed_span > original_span * 0.9

        # 缺口區塊裡任何一個時間點都不應該落到消失前的靜音區間之外太遠。
        for i in range(block_start_index, block_end_index + 1):
            assert abs(smoothed[i, 0] - beats[i, 0]) < 0.5
