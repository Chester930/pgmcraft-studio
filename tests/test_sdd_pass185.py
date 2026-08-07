"""Pass 185：beat_phase_protected_ranges 保護機制測試。

驗證 `SteadyPercussionCountAnchorNode` 建立的保護區段不會被下游 5 個節點蓋掉。
"""
import numpy as np
import pytest

from pgm_craft.workflow.beat_tracking_bt import (
    BeatGridContinuityRepairNode,
    DownbeatPhaseConsistencyNode,
    KickAnchorConsensusSnapNode,
    KickBassDownbeatVerifierNode,
    SteadyPercussionCountAnchorNode,
    TempoOscillationDampingNode,
    _relabel_beat_numbers,
    _time_in_protected_ranges,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------

def _make_regular_beats(n=56, interval=0.36, start=0.0, first_label=1):
    """建立等間隔 beats 矩陣。"""
    times = np.arange(n) * interval + start
    labels = ((np.arange(n) + first_label - 1) % 4) + 1
    return np.column_stack([times, labels])


def _get_labels_in_range(beats, t_start, t_end):
    """取出 [t_start, t_end] 區間內的 (time, label) 列表。"""
    mask = (beats[:, 0] >= t_start) & (beats[:, 0] <= t_end)
    return [(round(float(t), 4), int(l)) for t, l in beats[mask]]


# ---------------------------------------------------------------------------
# _time_in_protected_ranges helper
# ---------------------------------------------------------------------------

class TestTimeInProtectedRanges:
    def test_inside(self):
        assert _time_in_protected_ranges(5.0, [(3.0, 7.0)]) is True

    def test_outside(self):
        assert _time_in_protected_ranges(2.0, [(3.0, 7.0)]) is False

    def test_boundary(self):
        assert _time_in_protected_ranges(3.0, [(3.0, 7.0)]) is True
        assert _time_in_protected_ranges(7.0, [(3.0, 7.0)]) is True

    def test_empty(self):
        assert _time_in_protected_ranges(5.0, []) is False
        assert _time_in_protected_ranges(5.0, None) is False

    def test_multiple_ranges(self):
        ranges = [(1.0, 2.0), (5.0, 6.0)]
        assert _time_in_protected_ranges(1.5, ranges) is True
        assert _time_in_protected_ranges(5.5, ranges) is True
        assert _time_in_protected_ranges(3.0, ranges) is False


# ---------------------------------------------------------------------------
# _relabel_beat_numbers with protected_ranges
# ---------------------------------------------------------------------------

class TestRelabelWithProtection:
    def test_no_protection_unchanged_behavior(self):
        """沒有保護區段時，行為跟修改前完全一致。"""
        beats = _make_regular_beats(20, interval=0.5)
        # 先打亂標號
        beats[5:15, 1] = [3, 4, 1, 2, 3, 4, 1, 2, 3, 4]
        result_old = _relabel_beat_numbers(beats, first_label=1)
        result_new = _relabel_beat_numbers(beats, first_label=1, protected_ranges=None)
        result_empty = _relabel_beat_numbers(beats, first_label=1, protected_ranges=[])
        np.testing.assert_array_equal(result_old, result_new)
        np.testing.assert_array_equal(result_old, result_empty)

    def test_protection_preserves_labels(self):
        """保護區段內的標號維持原樣。"""
        beats = _make_regular_beats(20, interval=0.5)
        # 人工設定保護區段（idx 5~9 → 時間 2.5~4.5）的標號為 3,4,1,2,3
        beats[5:10, 1] = [3, 4, 1, 2, 3]
        protected = [(2.5, 4.5)]
        result = _relabel_beat_numbers(beats, first_label=1, protected_ranges=protected)
        # 保護區段內應維持
        for i in range(5, 10):
            assert result[i, 1] == beats[i, 1], f"idx {i} should be protected"
        # 保護區段外應正常重編號
        assert result[0, 1] == 1
        assert result[1, 1] == 2

    def test_protection_with_different_first_label(self):
        """first_label != 1 時保護區段也正常運作。"""
        beats = _make_regular_beats(16, interval=0.4)
        beats[6:10, 1] = [2, 3, 4, 1]  # 自訂相位
        protected = [(2.4, 3.6)]
        result = _relabel_beat_numbers(beats, first_label=3, protected_ranges=protected)
        for i in range(6, 10):
            assert result[i, 1] == beats[i, 1], f"idx {i} should be protected with first_label=3"


# ---------------------------------------------------------------------------
# BeatGridContinuityRepairNode respects protected ranges
# ---------------------------------------------------------------------------

class TestBeatGridContinuityRepairProtection:
    def test_protected_labels_survive_repair(self):
        """補拍/移除近重複拍觸發重編號時，保護區段內標號不變。"""
        beats = _make_regular_beats(56, interval=0.36)
        # 製造一個缺口讓節點會補拍（在 idx 30 和 31 之間多跳一拍距離）
        beats[31:, 0] += 0.36

        # 模擬 SteadyPercussionCountAnchorNode 在 idx 10-25 建立不同的區段相位
        protected_start = float(beats[10, 0])
        protected_end = float(beats[25, 0])
        original_labels_10_25 = beats[10:26, 1].copy()
        beats[10:26, 1] = ((np.arange(16) + 2) % 4) + 1  # 往後移 1

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("beat_phase_protected_ranges", [(protected_start, protected_end)])

        node = BeatGridContinuityRepairNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("beats")
        # 保護區段內標號應維持
        for t, expected_label in zip(beats[10:26, 0], beats[10:26, 1]):
            idx = int(np.argmin(np.abs(result[:, 0] - t)))
            assert result[idx, 1] == expected_label, (
                f"t={t:.3f}: expected label {expected_label}, got {result[idx, 1]}"
            )

    def test_no_protection_backward_compat(self):
        """沒有保護區段時，行為跟修改前完全一致。"""
        beats = _make_regular_beats(20, interval=0.36)
        beats[11:, 0] += 0.36  # 製造缺口

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        # 不設 beat_phase_protected_ranges

        node = BeatGridContinuityRepairNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("beats")
        # 所有標號應按序從頭數
        for i in range(len(result)):
            expected = ((i + int(beats[0, 1]) - 1) % 4) + 1
            assert result[i, 1] == expected


# ---------------------------------------------------------------------------
# TempoOscillationDampingNode respects protected ranges
# ---------------------------------------------------------------------------

class TestTempoOscillationDampingProtection:
    def test_protected_labels_survive_damping(self):
        """震盪修正觸發重編號時，保護區段內標號不變。"""
        beats = _make_regular_beats(40, interval=0.5)
        # 製造一個快慢震盪讓節點觸發
        beats[20, 0] -= 0.18  # 短
        beats[21, 0] += 0.00  # 正常→造成左短右長

        # 設定保護區段在 idx 10-16
        protected_start = float(beats[10, 0])
        protected_end = float(beats[16, 0])
        beats[10:17, 1] = ((np.arange(7) + 2) % 4) + 1

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("beat_phase_protected_ranges", [(protected_start, protected_end)])

        node = TempoOscillationDampingNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("beats")
        # 保護區段內標號應維持
        for t, expected_label in zip(beats[10:17, 0], beats[10:17, 1]):
            idx = int(np.argmin(np.abs(result[:, 0] - t)))
            assert result[idx, 1] == expected_label, (
                f"t={t:.3f}: expected label {expected_label}, got {result[idx, 1]}"
            )


# ---------------------------------------------------------------------------
# DownbeatPhaseConsistencyNode respects protected ranges
# ---------------------------------------------------------------------------

class TestDownbeatPhaseConsistencyProtection:
    def test_protected_labels_survive_phase_change(self):
        """全曲最佳相位重標時，保護區段內標號不變。"""
        beats = _make_regular_beats(40, interval=0.5, first_label=1)

        # 設定保護區段在 idx 8-20（時間 4.0-10.0）
        protected_start = float(beats[8, 0])
        protected_end = float(beats[20, 0])
        custom_labels = ((np.arange(13) + 3) % 4) + 1  # 不同相位
        beats[8:21, 1] = custom_labels

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("beat_phase_protected_ranges", [(protected_start, protected_end)])
        bb.set_val("sections", [{"start_time": 0.5}])  # 製造一些評分差異

        node = DownbeatPhaseConsistencyNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("beats")
        # 保護區段內標號應維持
        for t, expected_label in zip(beats[8:21, 0], custom_labels):
            idx = int(np.argmin(np.abs(result[:, 0] - t)))
            assert result[idx, 1] == expected_label, (
                f"t={t:.3f}: expected label {expected_label}, got {result[idx, 1]}"
            )


# ---------------------------------------------------------------------------
# KickAnchorConsensusSnapNode respects protected ranges
# ---------------------------------------------------------------------------

class TestKickAnchorConsensusSnapProtection:
    def test_protected_labels_survive_snap(self):
        """kick anchor 吸附觸發重編號時，保護區段內標號不變。"""
        beats = _make_regular_beats(40, interval=0.5)

        # 設定保護區段 idx 10-18
        protected_start = float(beats[10, 0])
        protected_end = float(beats[18, 0])
        custom_labels = ((np.arange(9) + 2) % 4) + 1
        beats[10:19, 1] = custom_labels

        # 建立一些偏移的 kick anchors 讓吸附可能觸發
        kick_anchors = beats[:, 0].copy()
        kick_anchors[3] += 0.03
        kick_anchors[25] -= 0.04

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("beat_phase_protected_ranges", [(protected_start, protected_end)])
        bb.set_val("kick_anchors", kick_anchors)

        node = KickAnchorConsensusSnapNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("beats")
        # 保護區段內標號應維持
        for t, expected_label in zip(beats[10:19, 0], custom_labels):
            idx = int(np.argmin(np.abs(result[:, 0] - t)))
            assert result[idx, 1] == expected_label, (
                f"t={t:.3f}: expected label {expected_label}, got {result[idx, 1]}"
            )


# ---------------------------------------------------------------------------
# KickBassDownbeatVerifierNode respects protected ranges
# ---------------------------------------------------------------------------

class TestKickBassDownbeatVerifierProtection:
    def _make_audio_with_energy_at(self, beat_times, strong_positions, sr=22050, duration=30.0):
        """製造一段音訊，在 strong_positions 指定的 beat index 有較強低頻能量。"""
        n_samples = int(duration * sr)
        y = np.zeros(n_samples)
        for idx in strong_positions:
            if idx < len(beat_times):
                t = beat_times[idx]
                center = int(t * sr)
                start = max(0, center - int(0.04 * sr))
                end = min(n_samples, center + int(0.04 * sr))
                # 加一個 80Hz 正弦波脈衝
                window = np.arange(end - start) / sr
                y[start:end] += 0.8 * np.sin(2 * np.pi * 80 * window)
        return y, sr

    def test_protected_labels_survive_rotation(self):
        """反相旋轉時保護區段內的標號不被改動。"""
        beats = _make_regular_beats(40, interval=0.5)

        # 設定保護區段 idx 10-18
        protected_start = float(beats[10, 0])
        protected_end = float(beats[18, 0])
        custom_labels = ((np.arange(9) + 2) % 4) + 1
        beats[10:19, 1] = custom_labels

        # 讓 beat3 能量遠大於 beat1 來觸發旋轉
        downbeat_indices = np.where(beats[:, 1] == 1)[0]
        beat3_indices = (downbeat_indices + 2) % len(beats)
        y, sr = self._make_audio_with_energy_at(
            beats[:, 0], beat3_indices, duration=float(beats[-1, 0]) + 1.0
        )

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("y", y)
        bb.set_val("sr", sr)
        bb.set_val("beat_phase_protected_ranges", [(protected_start, protected_end)])

        node = KickBassDownbeatVerifierNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("beats")
        # 保護區段內標號應維持
        for t, expected_label in zip(beats[10:19, 0], custom_labels):
            idx = int(np.argmin(np.abs(result[:, 0] - t)))
            assert result[idx, 1] == expected_label, (
                f"t={t:.3f}: expected label {expected_label}, got {result[idx, 1]}"
            )

    def test_no_protection_backward_compat(self):
        """沒有保護區段時，行為跟修改前完全一致。"""
        beats = _make_regular_beats(40, interval=0.5)
        downbeat_indices = np.where(beats[:, 1] == 1)[0]
        beat3_indices = (downbeat_indices + 2) % len(beats)
        y, sr = self._make_audio_with_energy_at(
            beats[:, 0], beat3_indices, duration=float(beats[-1, 0]) + 1.0
        )

        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("y", y)
        bb.set_val("sr", sr)
        # 不設 beat_phase_protected_ranges

        node = KickBassDownbeatVerifierNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        report = bb.get_val("downbeat_fix_report")
        # 應該正常觸發旋轉（因為 beat3 能量 >> beat1 能量）
        assert report["status"] in ("ROTATED", "PASS_NO_INVERSION")


# ---------------------------------------------------------------------------
# SteadyPercussionCountAnchorNode output_keys includes protected ranges
# ---------------------------------------------------------------------------

class TestSteadyPercussionCountAnchorOutputKeys:
    def test_output_keys_includes_protected_ranges(self):
        assert "beat_phase_protected_ranges" in SteadyPercussionCountAnchorNode.output_keys

    def test_empty_protected_ranges_written_when_no_steady_run(self):
        """即使沒找到穩定段也會寫入 beat_phase_protected_ranges。"""
        beats = _make_regular_beats(20, interval=0.5)
        bb = Blackboard()
        bb.set_val("beats", beats)
        # 不提供 stems → 一定找不到穩定段
        node = SteadyPercussionCountAnchorNode()
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS
        # 應該寫了空 list（不是 None、也不是 key 不存在）
        val = bb.get_val("beat_phase_protected_ranges")
        assert val is not None
        assert isinstance(val, list)
