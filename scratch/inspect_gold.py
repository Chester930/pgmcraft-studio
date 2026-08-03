import json
import numpy as np

report_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\module3_pipeline_report.json"
with open(report_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== 1. Measure Map 前 15 個小節 ===")
mmap = data.get("measure_map", [])
for m in mmap[:15]:
    st = m.get("start_time", 0.0)
    et = m.get("end_time", 0.0)
    dur = et - st
    bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
    print(f"Measure {m.get('measure'):2d}: {st:6.3f}s ~ {et:6.3f}s | Duration: {dur:5.3f}s | BPM: {bpm:5.1f}")

print("\n=== 2. BarStart v2 決策報告與證據 ===")
bv2 = data.get("barstart_v2_report", {})
print("v2 Status:", bv2.get("status"))

decisions = bv2.get("bar_start_decision_report", [])
print(f"Total decisions: {len(decisions)}")
for d in decisions[:10]:
    print(d)

print("\n=== 3. Beats 網格與 Refined Beats 前 20 點 ===")
rbeats = data.get("refined_beats", [])
print(f"Total refined beats: {len(rbeats)}")
for rb in rbeats[:20]:
    print(f"  Beat {rb[1]}: {rb[0]:.3f}s")
