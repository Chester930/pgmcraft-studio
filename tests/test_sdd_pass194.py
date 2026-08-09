"""
SDD Pass 194 — 讓 MeasureMapNode 的全曲 4/4 拍相位補全尊重
beat_phase_protected_ranges

背景：
Pass 193 的 `_ensure_44_phase_continuity` 無條件整曲機械式重推 1-2-3-4
標號（以全曲第一個 beat==1 為基準），完全沒有讀取 `beat_phase_protected_
ranges`——把 Pass 181-191 花了十輪反覆驗證、鎖定在真實鼓點證據上的錨定
相位整段蓋掉。直接核對真實資料：Pass 184/186 驗證過的 18.563s/20.014s
hi-hat 重音，在 Pass 193 真實輸出裡被偏移了一整拍（beat-1 變成落在
18.953s/20.359s）。詳見 docs/PASS-194-PHASE-CONTINUITY-RESPECTS-PROTECTED-
RANGES-TASK.md。

本測試驗證：
1. 保護區段內的標號（真實證據錨定）完全不被機械式補全覆蓋。
2. 保護區段之間的空隙依然平滑做機械式 1-2-3-4 補全（Pass 193 的效果
   保留），只在進入保護區段那一拍允許相位跳躍。
3. 沒有任何保護區段時，退回 Pass 193 原本的行為（向後相容）。
4. 真實案例回歸：18-20 秒 hi-hat 錨點的標號在補全後依然正確。
"""

from pgm_craft.workflow.audio_nodes import MeasureMapNode


def _beat_rows(times, labels):
    return [{"time": t, "beat": b} for t, b in zip(times, labels)]


class TestSDDPass194PhaseContinuityRespectsProtectedRanges:

    def test_protected_range_labels_untouched(self):
        """保護區段內的標號（就算跟機械式推算的相位不一致）完全不被覆蓋。"""
        node = MeasureMapNode()
        beat_sec = 0.36
        times = [round(i * beat_sec, 6) for i in range(16)]
        # 全部先填成不相關的錯誤標號，只有保護區段（index 9-12）填真實錨定
        # 標號 [1,2,3,4]——刻意跟該區段的陣列索引自然相位（9%4=1 -> 應為2）
        # 不一致，藉此驗證這是「證據優先」而不是「index 剛好對齊」。
        labels = [0] * 16
        for i, b in zip(range(9, 13), [1, 2, 3, 4]):
            labels[i] = b
        rows = _beat_rows(times, labels)
        protected_ranges = [(times[9], times[12])]

        fixed = node._ensure_44_phase_continuity(rows, protected_ranges)

        assert [fixed[i]["beat"] for i in range(9, 13)] == [1, 2, 3, 4]

    def test_free_gap_continues_smoothly_from_anchor(self):
        """保護區段之外的空隙，依然平滑做機械式 1-2-3-4 補全（前後都連貫）。"""
        node = MeasureMapNode()
        beat_sec = 0.36
        times = [round(i * beat_sec, 6) for i in range(16)]
        labels = [0] * 16
        for i, b in zip(range(9, 13), [1, 2, 3, 4]):
            labels[i] = b
        rows = _beat_rows(times, labels)
        protected_ranges = [(times[9], times[12])]

        fixed = node._ensure_44_phase_continuity(rows, protected_ranges)
        beats_out = [r["beat"] for r in fixed]

        # 整段 16 拍應該是一個連貫、無斷點的 1-2-3-4 循環（保護區段本身
        # 的相位基準點可能跟自然 index 相位不同，但前後銜接必須平滑）。
        for i in range(1, 16):
            expected_next = (beats_out[i - 1] % 4) + 1
            assert beats_out[i] == expected_next, f"index {i} 斷點：{beats_out}"

    def test_two_protected_ranges_each_preserved_independently(self):
        """兩段各自獨立錨定、彼此相位不對齊的保護區段，都各自完整保留，
        中間空隙只跟隨前一個錨點延伸，不會被後一個錨點提前干擾。"""
        node = MeasureMapNode()
        beat_sec = 0.36
        times = [round(i * beat_sec, 6) for i in range(24)]
        labels = [0] * 24
        for i, b in zip(range(2, 6), [1, 2, 3, 4]):
            labels[i] = b
        # 第二段刻意用不對齊的相位基準（模擬跟前段不同來源的獨立錨定）
        for i, b in zip(range(18, 22), [3, 4, 1, 2]):
            labels[i] = b
        rows = _beat_rows(times, labels)
        protected_ranges = [(times[2], times[5]), (times[18], times[21])]

        fixed = node._ensure_44_phase_continuity(rows, protected_ranges)
        beats_out = [r["beat"] for r in fixed]

        assert beats_out[2:6] == [1, 2, 3, 4]
        assert beats_out[18:22] == [3, 4, 1, 2]
        # 空隙（6-17）跟隨第一段連貫延伸，不受第二段影響
        for i in range(7, 18):
            expected_next = (beats_out[i - 1] % 4) + 1
            assert beats_out[i] == expected_next

    def test_no_protected_ranges_falls_back_to_pass193_behavior(self):
        """沒有任何保護區段時，退回 Pass 193 原本的整曲機械式補全（向後相容）。"""
        node = MeasureMapNode()
        beat_rows = [
            {"time": 0.0, "beat": 1},
            {"time": 0.36, "beat": 2},
            {"time": 0.72, "beat": 3},
            {"time": 1.08, "beat": 4},
            {"time": 1.44, "beat": 2},  # 本該是 1
            {"time": 1.80, "beat": 3},
            {"time": 2.16, "beat": 4},
            {"time": 2.52, "beat": 2},
        ]

        fixed_rows = node._ensure_44_phase_continuity(beat_rows, None)

        assert [r["beat"] for r in fixed_rows] == [1, 2, 3, 4, 1, 2, 3, 4]

    def test_real_captured_1820s_scenario_beat1_preserved(self):
        """真實案例回歸：18-20 秒 hi-hat 五連拍錨點（Pass 184/186 驗證過的
        18.563s/20.014s 是 beat 1），在補全後這兩個時間點依然標記為 beat 1，
        不會被機械式補全偏移成 beat 3/4（Pass 193 的真實回歸問題）。"""
        node = MeasureMapNode()
        beat_sec = 0.3606
        # 模擬前後各補幾拍，中間放真實錨定的五連拍（1,2,3,4,1）
        times = [round(17.46 + i * beat_sec, 6) for i in range(10)]
        anchor_times = [18.563, 18.934, 19.294, 19.642, 20.014]
        anchor_labels = [1, 2, 3, 4, 1]

        rows = _beat_rows(times, [0] * len(times))
        # 插入真實錨定的拍點（取代最接近的模擬拍點，模擬真實時間）
        for t, b in zip(anchor_times, anchor_labels):
            idx = min(range(len(rows)), key=lambda i: abs(rows[i]["time"] - t))
            rows[idx]["time"] = t
            rows[idx]["beat"] = b
        rows = sorted(rows, key=lambda r: r["time"])
        protected_ranges = [(anchor_times[0] - 0.01, anchor_times[-1] + 0.01)]

        fixed = node._ensure_44_phase_continuity(rows, protected_ranges)

        by_time = {round(r["time"], 3): r["beat"] for r in fixed}
        assert by_time[round(anchor_times[0], 3)] == 1
        assert by_time[round(anchor_times[-1], 3)] == 1
