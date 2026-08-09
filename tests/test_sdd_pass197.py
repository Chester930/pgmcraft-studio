"""SDD Pass 197A — 全域 4/4 相位仲裁。"""

import numpy as np

from pgm_craft.workflow.audio_nodes import MeasureMapNode


def _rows(times, downbeats):
    downbeats = set(downbeats)
    return np.asarray([[time, 1 if index in downbeats else (index % 4) + 1]
                       for index, time in enumerate(times)])


class TestSDDPass197GlobalPhaseReconciliation:

    def test_realistic_two_beat_conflict_keeps_global_phase_winner(self):
        beat = 0.3647
        times = [76.367 + beat * index for index in range(20)]
        times[4] = 77.803
        times[6] = 78.542
        times[10] = 80.020
        node = MeasureMapNode()
        protected = [(times[4], times[4]), (times[6], times[6])]

        rows = node._normalize_beats(_rows(times, [0, 4, 6, 10, 14, 18]))
        indexes, decisions = node._reconcile_close_downbeats(
            rows, [0, 4, 6, 10, 14, 18], protected
        )

        assert 4 in indexes
        assert 6 not in indexes
        assert decisions[0]["reason"] == "global_44_phase_consistency"
        assert decisions[0]["winner_time"] == 77.803

    def test_natural_tempo_drift_four_beat_gaps_are_not_conflicts(self):
        """真實資料回驗發現的迴歸：bar 之間只要有 2-3% 的自然速度微幅波動
        （真實歌曲到處都有），用全域 median beat_sec 換算出的 distance_beats
        就會落在 3.85-3.99 這種「差一點點沒到 4.0」的區間。門檻抓太緊會把
        全曲幾乎每個正常 4 拍小節邊界都當成衝突仲裁掉一個 downbeat。"""
        bar_durations = [1.44, 1.40, 1.46, 1.42, 1.44]
        times = []
        downbeats = []
        t = 0.0
        for bar_duration in bar_durations:
            downbeats.append(len(times))
            interval = bar_duration / 4.0
            for _ in range(4):
                times.append(t)
                t += interval
        times.append(t)
        downbeats.append(len(times) - 1)

        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, downbeats))
        # 比照真實資料：SteadyPercussionCountAnchorNode 等上游節點通常會把
        # 大半首歌都標成 protected range，所以測試也要涵蓋整段，不能靠
        # 「沒有 protected_ranges 就直接跳過」的早期 return 迴避真正的門檻邏輯。
        protected = [(times[0], times[-1])]
        indexes, decisions = node._reconcile_close_downbeats(rows, downbeats, protected)

        assert indexes == downbeats
        assert decisions == []

    def test_clean_four_four_is_unchanged(self):
        beat = 0.36
        times = [beat * index for index in range(32)]
        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, [0, 4, 8, 12, 16, 20, 24, 28]))
        indexes, decisions = node._reconcile_close_downbeats(
            rows,
            [0, 4, 8, 12, 16, 20, 24, 28],
        )

        assert indexes == [0, 4, 8, 12, 16, 20, 24, 28]
        assert decisions == []

    def test_protected_endpoint_gap_inserts_middle_downbeat(self):
        beat = 0.36
        times = [beat * index for index in range(13)]
        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, [0, 8, 12]))
        rows[4]["beat"] = 2
        protected = [(times[0], times[0]), (times[8], times[8])]

        rows, decisions = node._interpolate_protected_gaps(rows, [0, 8, 12], protected)

        assert rows[4]["beat"] == 1
        assert decisions[0]["inserted_downbeats"] == [1.44]

    def test_gap_without_two_protected_endpoints_is_untouched(self):
        beat = 0.36
        times = [beat * index for index in range(13)]
        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, [0, 8, 12]))
        rows[4]["beat"] = 2

        rows, decisions = node._interpolate_protected_gaps(rows, [0, 8, 12], [])

        assert rows[4]["beat"] != 1
        assert decisions == []
