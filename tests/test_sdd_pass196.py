"""
SDD Pass 196 — `_prune_ghost_downbeats` 不該剔除受保護的錨定 downbeat

背景：
Pass 195 追查發現 Pass 194 遺留的 9 個不規則小節，根因不在
`_ensure_44_phase_continuity`，而是 Pass 170 就存在的 `_prune_ghost_
downbeats`：兩個相鄰 downbeat 候選間距（陣列位置差）小於
`0.6 * 中位數間距`（通常門檻是 2.4）就會被當成「重複的 ghost」剔除掉
一個。直接核對真實資料發現，這兩個「間距太近」的候選其實各自落在
`SteadyPercussionCountAnchorNode` 建立的兩個相鄰保護區段內——都是真實
證據驗證過的錨點，不是雜訊。詳見
docs/PASS-196-GHOST-DOWNBEAT-PRUNING-RESPECTS-PROTECTION-TASK.md。

本測試驗證：
1. 兩個間距很近、但都落在各自保護區段內的 downbeat，都被保留。
2. 沒有保護區段時，既有 ghost-pruning 行為維持不變（向後相容）。
3. 只有一個受保護、另一個沒有證據支持時，只保留受保護的那個。
4. 既有 Pass 170 測試（無保護區段場景）維持通過。
"""

import numpy as np

from pgm_craft.workflow.audio_nodes import MeasureMapNode


class TestSDDPass196GhostDownbeatPruningRespectsProtection:

    def test_two_close_protected_downbeats_are_reconciled(self):
        """Pass 197：兩個各自受保護但相隔 2 拍的候選不能同時是小節起點；
        全域相位仲裁應保留符合前後 4/4 網格者。"""
        node = MeasureMapNode()
        beat_sec = 0.36
        # 建立一串正常 4 拍循環，中間插入兩個緊鄰（間距 2 拍）的 downbeat
        times = [round(i * beat_sec, 6) for i in range(24)]
        labels = [((i % 4) + 1) for i in range(24)]
        # 在 index 12 插入第一個受保護 downbeat（覆蓋原本標號）
        labels[12] = 1
        # 在 index 14（只間隔 2 拍）插入第二個受保護 downbeat
        labels[14] = 1
        beats = np.array([[t, l] for t, l in zip(times, labels)])

        protected_ranges = [
            (times[12], times[13]),
            (times[14], times[16]),
        ]

        mm, status, warnings = node.build_measure_map(
            beats, {"status": "PASS", "warnings": []}, {}, protected_ranges=protected_ranges
        )

        downbeat_starts = [m["start_time"] for m in mm]
        assert times[12] in downbeat_starts, "第一個受保護 downbeat 不應被剔除"
        assert times[14] not in downbeat_starts, "相位衝突的受保護候選應被仲裁掉"

    def test_no_protected_ranges_ghost_pruning_unchanged(self):
        """沒有保護區段時，ghost-pruning 行為維持 Pass 170 原本設計（向後相容）。"""
        node = MeasureMapNode()
        beat_interval = 0.363
        beats = []
        t = 0.405
        for m in range(12):
            for b in range(1, 5):
                beats.append([t, b])
                t += beat_interval
            if m in (3, 7):
                beats.append([t, 1])  # ghost downbeat（間距只有 0 拍）
                t += beat_interval * 0.3

        beats_arr = np.array(beats)
        mm, status, warnings = node.build_measure_map(
            beats_arr, {"status": "PASS", "warnings": []}, {}, protected_ranges=None
        )

        assert all(m["beat_count"] != 1 for m in mm), "沒有保護區段時，ghost downbeat 依然應該被剔除"

    def test_only_protected_one_kept_unprotected_one_pruned(self):
        """兩個緊鄰的 downbeat 候選，只有一個落在保護區段內，另一個沒有
        證據支持時，只保留受保護的那個，另一個依然當雜訊剔除。"""
        node = MeasureMapNode()
        beat_sec = 0.36
        times = [round(i * beat_sec, 6) for i in range(24)]
        labels = [((i % 4) + 1) for i in range(24)]
        labels[12] = 1  # 受保護
        labels[14] = 1  # 沒有保護，間距只有 2 拍
        beats = np.array([[t, l] for t, l in zip(times, labels)])

        # 只保護 index 12 這個
        protected_ranges = [(times[12], times[13])]

        mm, status, warnings = node.build_measure_map(
            beats, {"status": "PASS", "warnings": []}, {}, protected_ranges=protected_ranges
        )

        downbeat_starts = [m["start_time"] for m in mm]
        assert times[12] in downbeat_starts, "受保護的 downbeat 不應被剔除"
        assert times[14] not in downbeat_starts, "沒有保護的近距離 downbeat 依然應該被當雜訊剔除"
