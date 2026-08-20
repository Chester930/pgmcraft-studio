"""
Pass 192 專用診斷：深入追查 10 個不規則小節的前後相鄰小節拍號與時間戳
"""

import os
import json
import glob

matches = glob.glob(r"outputs/pass191_default_pipeline_reverify/**/measure_map.json", recursive=True)
if not matches:
    print("找不到 Pass 191 的 measure_map.json")
    exit(1)

path = matches[0]
print("讀取 Pass 191 報告：", path)
with open(path, encoding="utf-8") as f:
    data = json.load(f)

m_map = data.get("measure_map", [])
print(f"總小節數：{len(m_map)}")

irregulars = [m for m in m_map if m.get("is_variable_length")]
print(f"不規則小節數：{len(irregulars)}")

for m in irregulars:
    idx = m["measure"] - 1
    prev_m = m_map[idx - 1] if idx > 0 else None
    next_m = m_map[idx + 1] if idx + 1 < len(m_map) else None
    
    print(f"\n==================================================")
    print(f"不規則小節 #{m['measure']}: beat_count={m['beat_count']}, start={m['start_time']}s, end={m['end_time']}s, source={m.get('source')}")
    if prev_m:
        print(f"  前一小節 #{prev_m['measure']}: beat_count={prev_m['beat_count']}, start={prev_m['start_time']}s, end={prev_m['end_time']}s")
    print(f"  目前小節拍點：", [(b["beat"], b["time"]) for b in m.get("beats", [])])
    if next_m:
        print(f"  後一小節 #{next_m['measure']}: beat_count={next_m['beat_count']}, start={next_m['start_time']}s, end={next_m['end_time']}s")
