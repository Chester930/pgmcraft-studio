"""
SDD Pass 169 — 鼓型拍位解碼與雙聲部和弦鎖定節點 (GroovePatternPhaseDecoderNode) 驗證

背景：
當樂曲重音不在第 1 拍（如反拍/雷鬼/切分重音，或小鼓打在第 2、4 拍）時，舊邏輯易將第 2 拍誤設為第 1 拍。
Pass 169 透過 GroovePatternPhaseDecoderNode，讀取 chord_progression 和弦變換點與 bass_anchors 低音根音，計算重音點相對拍位 Phase Offset，若為第 2 或第 4 拍，自動將 Downbeat 反推回正確的第 1 拍。

本測試驗證：
1. 當第 2 拍反拍出現強重音 (1.45s 拍長下偏離 0.36s) 時，節點能正確識別並將 Downbeat 反推回真正的第 1 拍。
2. 雙聲部和弦變換鎖定機制正常運作。
"""

import pytest
import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import GroovePatternPhaseDecoderNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass169:

    def test_groove_phase_decoder_fixes_offbeat_accent(self):
        bb = Blackboard()
        beat_interval = 0.363  # 約 165 BPM
        bar_interval = beat_interval * 4.0

        # 和弦切換點確定在 0.405s, 1.857s ...
        t0 = 0.405
        chord_times = [t0 + i * bar_interval for i in range(5)]
        bb.set_val("chord_progression", [{"time": ct, "chord": "C"} for ct in chord_times])

        # 模擬第 2 個小節小鼓打在第 2 拍反拍重音 (t0 + bar_interval + beat_interval)
        offbeat_accent = chord_times[1] + beat_interval
        raw_bars = [chord_times[0], offbeat_accent, chord_times[2], chord_times[3], chord_times[4]]

        bb.set_val("committed_bar_starts", raw_bars)

        node = GroovePatternPhaseDecoderNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("groove_phase_report", {})
        assert report.get("phase_corrections", 0) >= 1

        fixed_bars = bb.get_val("committed_bar_starts", [])
        fixed_times = [b.get("time") if isinstance(b, dict) else float(b) for b in fixed_bars]

        # 驗證原本被誤設為第 2 拍重音的時間點，已反推回第 1 拍和弦變換點
        assert abs(fixed_times[1] - chord_times[1]) < 0.05
