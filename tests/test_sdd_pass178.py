"""
SDD Pass 178 — GapReinforcementNode 缺口強化節點驗證

背景：
Pass 178 把 Pass 176 設計、Pass 177 在多軌審查工具（scratch Lane1-5）實測
驗證過的「逐輪疊加證據，只補救信心不足的缺口」機制，正式整合進 V1 產線，
成為 BeatFusionArbitratorNode 之後、精修守衛鏈最前面的 GapReinforcementNode。

本測試用合成音訊驗證三個核心行為：
1. 沒有缺口時完全不動 beats。
2. 缺口內有貝斯證據時，能疊加貝斯重新分析、改善缺口內的拍點準確度。
3. 缺口內完全沒有任何額外證據時，安全退回原始融合結果，不冒然採用更差的結果。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import GapReinforcementNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus

SR = 22050


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


class TestSDDPass178:

    def test_no_gaps_leaves_beats_untouched(self, tmp_path):
        duration = 8.0
        true_times = list(np.arange(0.0, duration, 0.5))
        kick_y = _click_train(true_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)

        beats = np.array([[t, (i % 4) + 1] for i, t in enumerate(true_times)])

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("beat_fusion_report", {"track_b_spans": []})
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = GapReinforcementNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("gap_reinforcement_report")
        assert report["status"] == "NO_GAPS"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)

    def test_reinforces_gap_using_bass_evidence(self, tmp_path):
        duration = 12.0
        # 鼓：0-4s、8-12s 正常打點，4-8s 靜音（缺口，模擬無鼓前奏/間奏）
        drum_times = [t for t in np.arange(0.0, duration, 0.5) if t < 4.0 or t >= 8.0]
        kick_y = _click_train(drum_times, duration, freq=150.0)

        # 貝斯：全曲持續每 0.5 秒一個脈衝，包含缺口區間——缺口裡唯一的證據來源
        bass_times = list(np.arange(0.0, duration, 0.5))
        bass_y = _click_train(bass_times, duration, freq=80.0, decay=25.0)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        bass_dir = tmp_path / "bass"
        bass_dir.mkdir()
        sf.write(str(bass_dir / "bass.wav"), bass_y, SR)
        # 品質守門用的中性真相來源（優先讀完整無人聲混音，見
        # GapReinforcementNode._is_improvement）——沒有這個檔案，守門會退回
        # 只用鼓聲，但缺口裡本來就沒有鼓聲，會讓補強前後永遠都測不出差異。
        sf.write(str(tmp_path / "no_vocals.wav"), kick_y + bass_y, SR)

        # 模擬 V1 融合後的原始拍點：0-4s、8-12s 對，4-8s 是錯的（等速內插偏移 0.2 秒）
        good_times = [t for t in np.arange(0.0, duration, 0.5) if t < 4.0 or t >= 8.0]
        bad_times = [t + 0.2 for t in np.arange(4.0, 8.0, 0.5)]
        all_times = sorted(good_times + bad_times)
        beats = np.array([[t, (i % 4) + 1] for i, t in enumerate(all_times)])

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("beat_fusion_report", {
            "track_b_spans": [{"start_time": 4.0, "end_time": 8.0, "beat_count": 8, "reason": "low_rhythm_energy"}]
        })
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = GapReinforcementNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("gap_reinforcement_report")
        assert report["gap_count"] >= 1

        new_beats = bb.get_val("beats")
        gap_new_times = [row[0] for row in new_beats if 4.0 <= row[0] < 8.0]
        gap_old_times = [t for t in all_times if 4.0 <= t < 8.0]

        def avg_min_dist(times, ref):
            if not times:
                return 999.0
            return float(np.mean([min(abs(t - r) for r in ref) for t in times]))

        # 補強後的拍點應該比原本偏移 0.2 秒的錯誤拍點，更接近真實貝斯脈衝時間
        assert avg_min_dist(gap_new_times, bass_times) < avg_min_dist(gap_old_times, bass_times)

    def test_no_evidence_falls_back_to_original(self, tmp_path):
        duration = 12.0
        drum_times = [t for t in np.arange(0.0, duration, 0.5) if t < 4.0 or t >= 8.0]
        kick_y = _click_train(drum_times, duration, freq=150.0)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        # 故意不提供任何 bass/chord/melody/instrumental stem

        good_times = [t for t in np.arange(0.0, duration, 0.5) if t < 4.0 or t >= 8.0]
        bad_times = [t + 0.2 for t in np.arange(4.0, 8.0, 0.5)]
        all_times = sorted(good_times + bad_times)
        beats = np.array([[t, (i % 4) + 1] for i, t in enumerate(all_times)])

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("beat_fusion_report", {
            "track_b_spans": [{"start_time": 4.0, "end_time": 8.0, "beat_count": 8, "reason": "low_rhythm_energy"}]
        })
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = GapReinforcementNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("gap_reinforcement_report")
        assert report["status"] == "REJECTED_NOT_BETTER"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)
