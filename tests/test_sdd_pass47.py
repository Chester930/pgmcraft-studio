import unittest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import ReEntryReAnchoringNode
from pgm_craft.workflow.audio_nodes import DownbeatRefineNode


def make_beats(n, bpm=120.0):
    interval = 60.0 / bpm
    timestamps = np.arange(n) * interval
    beat_numbers = (np.arange(n) % 4) + 1
    return np.column_stack([timestamps, beat_numbers])


def make_beats_all_ones(n):
    timestamps = np.linspace(0, n * 0.5, n)
    beat_numbers = np.ones(n, dtype=int)
    return np.column_stack([timestamps, beat_numbers])


class TestReEntryReAnchoringNodeV2(unittest.TestCase):

    def test_dense_kicks_all_drum_no_mass_reanchoring(self):
        """全程有鼓：280 個 kick 不應造成 beat=1 全部被覆蓋"""
        node = ReEntryReAnchoringNode()
        beats = make_beats(200)
        sr = 22050
        y = np.random.randn(int(50 * sr)).astype(np.float32) * 0.1
        kick_times = np.arange(0, 50.0, 0.18)
        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("kick_anchors", kick_times)
        bb.set_val("y_rhythm", y)
        bb.set_val("sr_rhythm", sr)
        node.execute(bb)
        result = bb.get_val("beats")
        beat_numbers = result[:, 1].astype(int)
        count_ones = int(np.sum(beat_numbers == 1))
        self.assertGreater(count_ones, 30)
        self.assertLess(count_ones, 120)

    def test_cooldown_prevents_double_reanchoring(self):
        """冷卻期：2s 內只保留第一個邊緣"""
        node = ReEntryReAnchoringNode()
        edges = [5.0, 5.8, 6.3, 10.0, 12.5]
        result = node._apply_cooldown(edges)
        self.assertEqual(result[0], 5.0)
        self.assertEqual(result[1], 10.0)
        self.assertEqual(result[2], 12.5)
        self.assertEqual(len(result), 3)

    def test_cooldown_empty_input(self):
        node = ReEntryReAnchoringNode()
        self.assertEqual(node._apply_cooldown([]), [])

    def test_interval_based_edges_detects_reentry(self):
        """kick 間距突然縮短應偵測為 re-entry"""
        node = ReEntryReAnchoringNode()
        kick_times = [0.5, 1.0, 1.5, 8.0, 12.0, 15.5, 16.0, 16.5, 17.0]
        edges = node._interval_based_edges(kick_times)
        self.assertTrue(any(14.0 <= e <= 17.5 for e in edges),
            f"應在 14-18s 偵測到 re-entry，actual: {edges}")

    def test_no_beats_returns_success(self):
        node = ReEntryReAnchoringNode()
        bb = Blackboard()
        bb.set_val("beats", None)
        bb.set_val("kick_anchors", np.array([1.0, 2.0]))
        self.assertEqual(node.execute(bb), NodeStatus.SUCCESS)

    def test_no_kick_anchors_returns_success(self):
        node = ReEntryReAnchoringNode()
        bb = Blackboard()
        bb.set_val("beats", make_beats(40))
        bb.set_val("kick_anchors", None)
        self.assertEqual(node.execute(bb), NodeStatus.SUCCESS)

    def test_no_consecutive_ones_after_reanchoring(self):
        """重錨後不應出現連續 3 個以上 beat=1"""
        node = ReEntryReAnchoringNode()
        beats = make_beats(200, bpm=120.0)
        sr = 22050
        y = np.zeros(int(50 * sr), dtype=np.float32)
        for s, e in [(0, 10), (20, 30), (40, 50)]:
            y[int(s * sr):int(e * sr)] = 0.1
        kick_times = np.concatenate([
            np.arange(0.5, 10.0, 0.5),
            np.arange(20.5, 30.0, 0.5),
            np.arange(40.5, 50.0, 0.5),
        ])
        bb = Blackboard()
        bb.set_val("beats", beats.copy())
        bb.set_val("kick_anchors", kick_times)
        bb.set_val("y_rhythm", y)
        bb.set_val("sr_rhythm", sr)
        node.execute(bb)
        result = bb.get_val("beats")
        beat_numbers = result[:, 1].astype(int)
        consec = max_c = 0
        for bn in beat_numbers:
            if bn == 1:
                consec += 1
                max_c = max(max_c, consec)
            else:
                consec = 0
        self.assertLessEqual(max_c, 3, f"max consecutive beat=1: {max_c}")


class TestDownbeatRefineMedianFilter(unittest.TestCase):

    def test_mode_returns_four(self):
        node = DownbeatRefineNode()
        self.assertEqual(node._mode_measure_length([4, 4, 4, 4, 1, 4, 4, 1, 4, 4]), 4)

    def test_mode_ignores_out_of_range(self):
        node = DownbeatRefineNode()
        self.assertEqual(node._mode_measure_length([1, 1, 1, 4, 4]), 4)

    def test_mode_empty(self):
        node = DownbeatRefineNode()
        self.assertIsNone(node._mode_measure_length([]))

    def test_mode_all_invalid(self):
        node = DownbeatRefineNode()
        self.assertIsNone(node._mode_measure_length([1, 1, 1, 9, 10]))

    def test_rebuild_from_zero(self):
        node = DownbeatRefineNode()
        self.assertEqual(node._rebuild_downbeats_by_mode([0, 1, 2, 3], 4, 20), [0, 4, 8, 12, 16])

    def test_rebuild_with_offset(self):
        node = DownbeatRefineNode()
        self.assertEqual(node._rebuild_downbeats_by_mode([2, 3, 4], 4, 20), [2, 6, 10, 14, 18])

    def test_rebuild_empty(self):
        node = DownbeatRefineNode()
        self.assertEqual(node._rebuild_downbeats_by_mode([], 4, 20), [])

    def test_median_filter_fixes_mixed_abnormal(self):
        """
        混合輸入：多數小節長度為 4，少數為 1（超過 30% 異常）
        → median filter 以眾數=4 重建，輸出 measure_lengths 不應全為 1
        """
        node = DownbeatRefineNode()
        # 製造 beat_number 序列：多數 4 拍一循環，但前 50 拍被強制設 1（模擬 bug 後遺症）
        timestamps = np.linspace(0, 100 * 0.5, 100)
        beat_numbers = (np.arange(100) % 4) + 1  # 正常 1-2-3-4
        # 模擬前段 bug：前 40 拍全設為 1（造成 >30% 異常 downbeat）
        beat_numbers[:40] = 1
        beats = np.column_stack([timestamps, beat_numbers]).tolist()
        _, result = node.refine(beats)
        ml = result.get("measure_lengths", [])
        # 修正後 measure_lengths 不應全為 1
        self.assertTrue(len(ml) > 0, "應有小節長度資料")
        self.assertFalse(all(l == 1 for l in ml),
            f"Median filter 應修正異常小節，actual: {ml[:10]}")

    def test_pure_all_ones_mode_is_none(self):
        """全 1 輸入時 mode_measure_length 返回 None（無法修復，是正確行為）"""
        node = DownbeatRefineNode()
        # measure_lengths 全為 1，超出 MIN_REASONABLE=2，mode 應為 None
        self.assertIsNone(node._mode_measure_length([1] * 50))

    def test_correct_beats_pass(self):
        """正常 1-2-3-4 → status PASS"""
        node = DownbeatRefineNode()
        timestamps = np.linspace(0, 80 * 0.5, 80)
        beat_numbers = (np.arange(80) % 4) + 1
        beats = np.column_stack([timestamps, beat_numbers]).tolist()
        _, result = node.refine(beats)
        self.assertEqual(result["status"], "PASS")

    def test_abnormal_ratio_below_threshold(self):
        """20% 異常不應超過 30% 閾值"""
        node = DownbeatRefineNode()
        ml = [4, 4, 4, 4, 1]
        ratio = sum(1 for l in ml if l < 2 or l > 8) / len(ml)
        self.assertLess(ratio, 0.3)


if __name__ == "__main__":
    unittest.main()
