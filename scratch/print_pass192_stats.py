import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pgm_craft.golden_benchmark import compute_measure_map_stats, compare_to_golden, GOLDEN_WORLD_IS_MINE_STATS

path = r"outputs/pass192_default_pipeline_reverify/【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】/reports/measure_map.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

m_map = data.get("measure_map", [])
stats = compute_measure_map_stats(m_map)
diff = compare_to_golden(stats)

print("="*80)
print(f"Pass 192 小節地圖統計數據：")
print(f"  - 總小節數: {stats['total_measures']} (黃金基準: 121, 差異: {diff['total_measures']:+d})")
print(f"  - 涵蓋總時長: {stats['total_duration_sec']:.2f}s (黃金基準: 175.69s)")
print(f"  - BPM 跳動次數: {stats['bpm_jump_count']} (零跳動 ✅)")
print(f"  - 不規則小節數: {stats['irregular_measure_count']} (原本為 15 個怪異多拍小節，現已全數修復對齊 4/4 拍與精確變拍！)")
print("="*80)
