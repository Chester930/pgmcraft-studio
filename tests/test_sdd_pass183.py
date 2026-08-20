"""
SDD Pass 183 — KickSnarePulseNode 補上整個鼓軌交叉確認

背景：
Pass 182 修了 SteadyPercussionCountAnchorNode，使用者同意順便處理其他有
同樣架構缺口的節點。KickSnarePulseNode 產出的 kick_anchors/snare_anchors
被 ReEntryReAnchoringNode、DownbeatPhaseConsistencyNode、
KickAnchorConsensusSnapNode、DrumFillDetectionNode 等一整串下游節點共用，
卻完全只看細分軌，從未回頭比對整個鼓軌。詳見
docs/PASS-183-KICKSNAREPULSE-WHOLE-DRUM-TRACK-CROSSCHECK-TASK.md。

本測試驗證：
1. kick.wav 有乾淨脈衝、整軌在對應時間也有能量，錨點正常保留。
2. kick.wav 有乾淨脈衝、但整軌在對應時間完全沒有能量（模擬分離殘留假
   訊號），錨點被濾掉。
3. 沒有整軌檔案時完全跳過確認（向後相容既有行為）。
4. 無鼓區間 Sub-Bass 補位邏輯不受交叉確認影響——補位錨點本來就預期整軌
   沒有對應能量，不能被交叉確認反向淘汰。
"""

import os
import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import KickSnarePulseNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus

SR = 22050


def _pulse_train(times, duration_sec, sr=SR, freq=60.0, decay=20.0, amp=0.8):
    n = int(duration_sec * sr)
    y = np.zeros(n, dtype=np.float32)
    pulse_len = int(0.1 * sr)
    t_p = np.linspace(0, 0.1, pulse_len, endpoint=False)
    pulse = amp * np.sin(2 * np.pi * freq * t_p) * np.exp(-t_p * decay)
    for t in times:
        idx = int(t * sr)
        end = min(n, idx + pulse_len)
        actual = end - idx
        if actual > 0 and idx < n:
            y[idx:end] += pulse[:actual]
    return y


class TestSDDPass183KickSnarePulseWholeDrumTrackCrosscheck:

    def test_confirmed_kick_anchors_kept_with_matching_whole_track(self, tmp_path):
        duration = 4.0
        times = [0.0, 1.0, 2.0, 3.0]
        kick_y = _pulse_train(times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        # 整個鼓軌在同樣時間點也有對應能量（真實混音本來就有這些 kick）
        sf.write(str(drums_dir / "drums.wav"), kick_y, SR)

        bb = Blackboard()
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = KickSnarePulseNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        kick_anchors = bb.get_val("kick_anchors")
        assert len(kick_anchors) == 4

    def test_unconfirmed_kick_anchors_dropped_without_whole_track_energy(self, tmp_path):
        duration = 4.0
        times = [0.0, 1.0, 2.0, 3.0]
        kick_y = _pulse_train(times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)

        # 整個鼓軌在別的時間點有活動（不是完全空白的音軌），但在 kick 那些
        # 時間點完全沒有對應能量——這是真正可疑的分離殘留假訊號情境。
        unrelated_times = [0.5, 1.5, 2.5, 3.5]
        drums_y = _pulse_train(unrelated_times, duration)
        sf.write(str(drums_dir / "drums.wav"), drums_y, SR)

        bb = Blackboard()
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = KickSnarePulseNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        kick_anchors = bb.get_val("kick_anchors")
        assert len(kick_anchors) == 0

    def test_no_whole_track_file_skips_confirmation(self, tmp_path):
        """既有行為向後相容：沒有 drums.wav 時完全不做交叉確認。"""
        duration = 4.0
        times = [0.0, 1.0, 2.0, 3.0]
        kick_y = _pulse_train(times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        # 故意不提供 drums.wav

        bb = Blackboard()
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = KickSnarePulseNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        kick_anchors = bb.get_val("kick_anchors")
        assert len(kick_anchors) == 4

    def test_sub_bass_guard_not_affected_by_crosscheck(self, tmp_path):
        """無鼓區間 Sub-Bass 補位邏輯：補進來的錨點本來就預期整軌沒有對應
        能量，不能被交叉確認反向淘汰。"""
        duration = 8.0
        # 只有 2 個 kick（< 5，會觸發 Sub-Bass Guard）
        kick_times = [0.0, 1.0]
        kick_y = _pulse_train(kick_times, duration)

        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
        # 整個鼓軌只在 kick 出現的地方有能量，無鼓區間（4-8s）本來就沒有
        sf.write(str(drums_dir / "drums.wav"), kick_y, SR)

        bass_dir = tmp_path / "bass"
        bass_dir.mkdir()
        # 無鼓區間（4-8s）用貝斯低頻脈衝補位
        bass_times = [4.0, 5.0, 6.0, 7.0]
        bass_y = _pulse_train(bass_times, duration, freq=45.0)
        sf.write(str(bass_dir / "bass.wav"), bass_y, SR)

        bb = Blackboard()
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))

        node = KickSnarePulseNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        kick_anchors = sorted(bb.get_val("kick_anchors"))
        # 原本 2 個 kick 錨點應該都被整軌確認保留，加上 4 個貝斯補位錨點
        assert len(kick_anchors) == 6
        for t in bass_times:
            assert min(abs(t - ka) for ka in kick_anchors) < 0.15
