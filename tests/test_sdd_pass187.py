"""
SDD Pass 187 — 只保護「真的改動過標號」的區段，不保護無效區段

背景：
使用者實際試聽 Pass 186 真實完整管線輸出後回報「很多不完整的小節，沒有
走完四拍就跳下一個小節，節拍錯亂問題」。追查確認：這次真實跑法找到的 37
個套用錨點裡，只有 11 個（30%）套用前後真的改動了標號，其餘 26 個
（70%）套用前後標號完全沒變，卻依然被列入 `beat_phase_protected_ranges`，
平白多了交界處衝突風險。詳見
docs/PASS-187-PROTECT-ONLY-CHANGED-RANGES-TASK.md。

本測試驗證：
1. 套用後標號沒有實際改動的候選段，不會被列入 `beat_phase_protected_ranges`
   （但依然會出現在 `applied` 清單裡）。
2. 套用後標號真的改動的候選段，依然正確列入 `beat_phase_protected_ranges`，
   且 Pass 185 的保護機制依然生效。
3. 真實資料回歸：驗證保護區段數量確實下降，且目標區段的保護依然存在。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import (
    BeatGridContinuityRepairNode,
    SteadyPercussionCountAnchorNode,
)
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


def _beats_grid_sequential(duration_sec, beat_sec=BEAT_SEC):
    """從陣列開頭就是乾淨連貫的 1-2-3-4 循環（模擬套用錨點後標號不會改變
    的情境）。"""
    times = np.arange(0.0, duration_sec, beat_sec)
    return np.array([[t, (i % 4) + 1] for i, t in enumerate(times)])


def _beats_grid_wrong(duration_sec, beat_sec=BEAT_SEC, wrong_label=2):
    """全部標成同一個錯誤標號（模擬套用錨點後標號真的會改變的情境）。"""
    times = np.arange(0.0, duration_sec, beat_sec)
    return np.array([[t, wrong_label] for t in times])


class TestSDDPass187ProtectOnlyChangedRanges:

    def test_noop_anchor_not_protected(self, tmp_path):
        """候選段的相位剛好跟原本就有的標號一樣，套用後標號沒有實際改動，
        不應該被列入保護清單（但依然出現在 applied 清單）。"""
        duration = 12.0
        beats = _beats_grid_sequential(duration)  # 已經是乾淨連貫的循環
        grid_times = beats[:, 0]
        # idx 12 是 4 的倍數，陣列本來的自然標號是 (12%4)+1=1，
        # 跟錨點強制標記的 1 一致，套用後不會有任何改動。
        run_times = grid_times[12:16]
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
        assert len(report["applied"]) == 1  # 依然記錄有嘗試套用

        protected = bb.get_val("beat_phase_protected_ranges")
        assert protected == []  # 但沒有實際改動，不列入保護清單

    def test_real_change_anchor_still_protected(self, tmp_path):
        """候選段套用後標號真的改變了，依然正確列入保護清單，且下游節點
        依然會尊重這段。"""
        duration = 12.0
        beats = _beats_grid_wrong(duration)  # 全部錯誤標成同一個標號
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
        assert len(report["applied"]) == 1

        protected = bb.get_val("beat_phase_protected_ranges")
        assert len(protected) == 1

        # 驗證 Pass 185 的保護機制依然生效：BeatGridContinuityRepairNode
        # 觸發全曲重編號時，這段的標號不會被蓋掉。在保護區段之外（陣列尾端）
        # 製造一個缺口，觸發補拍。
        new_beats = bb.get_val("beats")
        times_extended = list(new_beats[:, 0])
        labels_extended = list(new_beats[:, 1])
        del_idx = len(times_extended) - 2  # 陣列尾端，遠離 idx 10-14 的保護區段
        del times_extended[del_idx]
        del labels_extended[del_idx]
        beats2 = np.array([[t, l] for t, l in zip(times_extended, labels_extended)])

        bb2 = Blackboard()
        bb2.set_val("beats", beats2)
        bb2.set_val("beat_phase_protected_ranges", protected)
        repair_node = BeatGridContinuityRepairNode()
        repair_node.execute(bb2)
        after = bb2.get_val("beats")

        timestamps = new_beats[:, 0]
        for t in run_times:
            idx_before = int(np.argmin(np.abs(new_beats[:, 0] - t)))
            idx_after = int(np.argmin(np.abs(after[:, 0] - t)))
            assert after[idx_after, 1] == new_beats[idx_before, 1]

    def test_mixed_scenario_only_changed_range_protected(self, tmp_path):
        """一個沒改動的候選段 + 一個真的改動的候選段，只有後者進保護清單。"""
        duration = 20.0
        beats = _beats_grid_sequential(duration)
        grid_times = beats[:, 0]

        # 第一段（idx 8-11，8 是 4 的倍數，自然標號本來就是 1,2,3,4）套用後不變
        noop_times = grid_times[8:12]
        # 第二段（idx 30-33）故意先弄錯，讓套用後真的改變
        beats[30:34, 1] = [3, 4, 1, 2]
        changed_times = grid_times[30:34]

        kick_y = _click_train(list(noop_times) + list(changed_times), duration)

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
        assert len(report["applied"]) == 2

        protected = bb.get_val("beat_phase_protected_ranges")
        assert len(protected) == 1
        prot_start, prot_end = protected[0]
        assert prot_start >= changed_times[0] - 0.01
