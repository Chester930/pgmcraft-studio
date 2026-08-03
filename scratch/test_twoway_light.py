import os
import json
import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import TwoWayAnchorBacktraceNode
from pgm_craft.workflow.nodes import Blackboard

# 讀取已存在的 committed_bar_starts 或 measure_map
gold_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\module3_pipeline_report.json"
pass167_path = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\comparison_test_pass167\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"

with open(pass167_path, "r", encoding="utf-8") as f:
    pass167_mmap = json.load(f)

bars = [m.get("start_time") for m in pass167_mmap]

bb = Blackboard()
bb.set_val("committed_bar_starts", bars)

node = TwoWayAnchorBacktraceNode()
node.execute(bb)

fixed_bars = bb.get_val("committed_bar_starts", [])
report = bb.get_val("twoway_backtrace_report", {})

print(f"=== 雙向確信錨點反推執行完畢 ===")
print(f"修復點數量: {report.get('corrections')}")

fixed_times = [b.get("time") if isinstance(b, dict) else float(b) for b in fixed_bars]

print("\n=== 修復後 0s ~ 32s (前奏區段) ===")
for i in range(len(fixed_times) - 1):
    t1 = fixed_times[i]
    t2 = fixed_times[i + 1]
    if t1 <= 32.0:
        dur = t2 - t1
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  Measure {i+1:2d}: {t1:6.3f}s ~ {t2:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")

print("\n=== 修復後 95s ~ 125s (間奏區段) ===")
for i in range(len(fixed_times) - 1):
    t1 = fixed_times[i]
    t2 = fixed_times[i + 1]
    if 95.0 <= t1 <= 125.0:
        dur = t2 - t1
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  Measure {i+1:2d}: {t1:6.3f}s ~ {t2:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")
