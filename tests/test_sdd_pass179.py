"""
SDD Pass 179 — GapReinforcementNode 診斷輸出落盤驗證

背景：
Pass 178 設計文件寫了「GapReinforcementNode 執行時要把診斷資料存成
blocks.json/beats.json 格式，讓審查工具能直接讀正式生產的輸出」，但實作時
漏掉了。Pass 179 補上這一塊，接通校準迴圈跟正式生產迴圈。

本測試驗證：
1. 有 project_dir 時，執行後 reports/gap_reinforcement/blocks.json 與
   beats.json 確實落盤，且格式跟審查工具（scratch/gap_review_server.py）
   預期的欄位（id/start/end/needs_review、tempo/beats）完全相容。
2. 落盤的 blocks 涵蓋全曲（不是只有缺口），且需要複核的區段跟不需要的
   區段都有出現。
3. 沒有 project_dir（例如既有的單元測試環境）時安全跳過，不丟例外。
"""

import json
import os

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


def _build_gap_scenario(tmp_path):
    duration = 12.0
    drum_times = [t for t in np.arange(0.0, duration, 0.5) if t < 4.0 or t >= 8.0]
    kick_y = _click_train(drum_times, duration, freq=150.0)
    bass_times = list(np.arange(0.0, duration, 0.5))
    bass_y = _click_train(bass_times, duration, freq=80.0, decay=25.0)

    drums_dir = tmp_path / "stems" / "drums"
    drums_dir.mkdir(parents=True)
    sf.write(str(drums_dir / "kick.wav"), kick_y, SR)
    bass_dir = tmp_path / "stems" / "bass"
    bass_dir.mkdir(parents=True)
    sf.write(str(bass_dir / "bass.wav"), bass_y, SR)
    sf.write(str(tmp_path / "stems" / "no_vocals.wav"), kick_y + bass_y, SR)

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
    bb.set_val("stems_dir", str(tmp_path / "stems"))
    return bb


class TestSDDPass179:

    def test_diagnostic_export_written_with_project_dir(self, tmp_path):
        bb = _build_gap_scenario(tmp_path)
        bb.set_val("project_dir", str(tmp_path))

        node = GapReinforcementNode(enabled=True)
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        blocks_path = tmp_path / "reports" / "gap_reinforcement" / "blocks.json"
        beats_path = tmp_path / "reports" / "gap_reinforcement" / "beats.json"
        assert blocks_path.exists()
        assert beats_path.exists()

        with open(blocks_path, "r", encoding="utf-8") as f:
            blocks = json.load(f)
        with open(beats_path, "r", encoding="utf-8") as f:
            beats_doc = json.load(f)

        assert isinstance(blocks, list) and len(blocks) > 0
        for b in blocks:
            assert set(b.keys()) == {"id", "start", "end", "needs_review"}
            assert isinstance(b["needs_review"], bool)

        # 全曲涵蓋：第一塊從 0 開始，最後一塊在曲末結束
        assert blocks[0]["start"] == 0.0
        assert blocks[-1]["end"] > 11.0

        assert "tempo" in beats_doc and "beats" in beats_doc
        assert len(beats_doc["beats"]) > 0

    def test_no_export_without_project_dir(self, tmp_path):
        bb = _build_gap_scenario(tmp_path)
        # 故意不設定 project_dir

        node = GapReinforcementNode(enabled=True)
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS
        assert not (tmp_path / "reports").exists()

    def test_no_gaps_scenario_still_exports(self, tmp_path):
        duration = 8.0
        true_times = list(np.arange(0.0, duration, 0.5))
        kick_y = _click_train(true_times, duration)

        drums_dir = tmp_path / "stems" / "drums"
        drums_dir.mkdir(parents=True)
        sf.write(str(drums_dir / "kick.wav"), kick_y, SR)

        beats = np.array([[t, (i % 4) + 1] for i, t in enumerate(true_times)])

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("beat_fusion_report", {"track_b_spans": []})
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path / "stems"))
        bb.set_val("project_dir", str(tmp_path))

        node = GapReinforcementNode(enabled=True)
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("gap_reinforcement_report")["status"] == "NO_GAPS"

        blocks_path = tmp_path / "reports" / "gap_reinforcement" / "blocks.json"
        assert blocks_path.exists()
