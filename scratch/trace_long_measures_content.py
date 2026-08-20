"""
追查 Pass 191 回驗結果中過長小節 (5拍, 6拍) 的拍點時間間隔與局部 BPM
"""

import os
import json
import glob

matches = glob.glob(r"outputs/pass191_default_pipeline_reverify/**/measure_map.json", recursive=True)
if not matches:
    print("找不到 measure_map.json")
    exit(1)

path = matches[0]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

m_map = data.get("measure_map", [])

for m in m_map:
    if m.get("is_variable_length") and m.get("beat_count", 0) > 4:
        print(f"\n過長小節 #{m['measure']} ({m['beat_count']} 拍): start={m['start_time']}s, end={m['end_time']}s")
        beats = m.get("beats", [])
        times = [b["time"] for b in beats]
        diffs = [round(times[i+1] - times[i], 4) for i in range(len(times)-1)]
        bpms = [round(60.0 / d, 1) if d > 0 else 0 for d in diffs]
        for i, b in enumerate(beats):
            d_str = f" (+{diffs[i]}s, ~{bpms[i]} BPM)" if i < len(diffs) else ""
            print(f"   拍 {b['beat']}: time={b['time']}s{d_str}")
