"""
Pass 171 — 黃金基準比對工具。

背景：
2026-07-30 16:30 產出的《World is Mine》click（早於 Pass 142「BarStart v2 扶正為預設」）
被使用者認定為本週音質最佳的一版。事後分析（見 docs/PASS-171-...-TASK.md）發現：
1. 該版其實不是 BarStart v2 產生的，而是舊版 BeatNet ensemble + downbeat 精修鏈產生，
   BarStart v2 當時只是 MERGED_DIAGNOSTIC_ONLY 旁路診斷。
2. 該版 measure_map 是 121 小節、全部 4/4、涵蓋完整 175.69 秒、零次 BPM 跳動 >35%。
3. 目前 BarStart v2 成為唯一決策來源後（Pass 142 之後），同曲重跑只剩 119 小節、
   171.39 秒，且尾奏最後一小節被截斷成 3 拍。

這個模組把「黃金基準」的統計數字固化下來，並提供跟任何 measure_map 比較的工具函式，
供 tests/test_sdd_pass171.py 與 scratch/run_pass171_variant_matrix.py 共用，
避免兩邊各自重算一套指標。
"""

import numpy as np

# 2026-07-30 16:30 黃金版《World is Mine》measure_map 統計數字（見 reports/measure_map.json）。
GOLDEN_WORLD_IS_MINE_STATS = {
    "song": "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】",
    "source_report": (
        r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
        r"\reports\measure_map.json"
    ),
    "generated_at": "2026-07-30T16:30:37",
    "total_measures": 121,
    "total_duration_sec": 175.693469,
    "avg_bpm": 164.7977949599164,
    "min_bpm": 147.6913079357616,
    "max_bpm": 181.59971186179172,
    "bpm_jump_count": 0,
    "irregular_measure_count": 0,
}


def compute_measure_map_stats(measure_map):
    """從 measure_map（list[dict]，每個 dict 至少有 start_time / beat_count）算出跟
    GOLDEN_WORLD_IS_MINE_STATS 同一組指標，方便直接比較。"""
    if not measure_map:
        return {
            "total_measures": 0,
            "total_duration_sec": 0.0,
            "avg_bpm": 0.0,
            "min_bpm": 0.0,
            "max_bpm": 0.0,
            "bpm_jump_count": 0,
            "irregular_measure_count": 0,
        }

    starts = [float(m["start_time"]) for m in measure_map]
    beat_counts = [int(m.get("beat_count", 4)) for m in measure_map]
    end_time = float(measure_map[-1].get("end_time", starts[-1]))

    durations = np.diff(starts) if len(starts) > 1 else np.array([])
    # 用每個小節自己的 beat_count 換算「4 拍等值時長」，才能跟固定 4/4 的 BPM 定義一致比較。
    normalized_durations = []
    for i, dur in enumerate(durations):
        bc = beat_counts[i] if beat_counts[i] > 0 else 4
        normalized_durations.append(dur * 4.0 / bc)
    normalized_durations = np.array(normalized_durations)

    bpms = 60.0 * 4.0 / normalized_durations if len(normalized_durations) else np.array([])
    bpm_jump_count = 0
    for i in range(len(bpms) - 1):
        if bpms[i] > 0 and abs(bpms[i + 1] - bpms[i]) / bpms[i] > 0.35:
            bpm_jump_count += 1

    irregular_measure_count = sum(1 for bc in beat_counts if bc != 4)

    return {
        "total_measures": len(measure_map),
        "total_duration_sec": round(end_time, 6),
        "avg_bpm": float(np.mean(bpms)) if len(bpms) else 0.0,
        "min_bpm": float(np.min(bpms)) if len(bpms) else 0.0,
        "max_bpm": float(np.max(bpms)) if len(bpms) else 0.0,
        "bpm_jump_count": int(bpm_jump_count),
        "irregular_measure_count": int(irregular_measure_count),
    }


def compare_to_golden(stats, golden=None):
    """回傳 candidate stats 相對於黃金基準的差異（正值代表比黃金版多/高）。"""
    golden = golden or GOLDEN_WORLD_IS_MINE_STATS
    keys = [
        "total_measures",
        "total_duration_sec",
        "avg_bpm",
        "min_bpm",
        "max_bpm",
        "bpm_jump_count",
        "irregular_measure_count",
    ]
    return {key: round(stats.get(key, 0) - golden.get(key, 0), 4) for key in keys}
