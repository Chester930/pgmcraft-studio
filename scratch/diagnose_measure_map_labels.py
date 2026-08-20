"""
診斷 measure_map.json 中 5/6/7 拍不規則小節的拍點標號與來源
"""

import os
import json
import glob

matches = glob.glob(r"outputs/pass190_default_pipeline_reverify/**/measure_map.json", recursive=True)
if not matches:
    print("找不到 measure_map.json")
    exit(1)

path = matches[0]
print("讀取：", path)
with open(path, encoding="utf-8") as f:
    data = json.load(f)

m_map = data.get("measure_map", [])
print(f"總小節數：{len(m_map)}")

for m in m_map:
    if m.get("is_variable_length"):
        print(f"\n小節 {m['measure']}: beat_count={m['beat_count']}, start={m['start_time']}s, end={m['end_time']}s")
        beats = m.get("beats", [])
        print("  拍點時間與標號：", [(b["beat"], b["time"]) for b in beats])
