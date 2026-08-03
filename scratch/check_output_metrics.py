import os
import json
import numpy as np

out_dir = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\comparison_test_pass167"
print("=== 檢查輸出資料夾內容 ===")
if os.path.exists(out_dir):
    for root, dirs, files in os.walk(out_dir):
        for f in files:
            p = os.path.join(root, f)
            print(os.path.relpath(p, out_dir), f"({os.path.getsize(p)} bytes)")

# 找尋 json report
report_p = None
for root, dirs, files in os.walk(out_dir):
    for f in files:
        if f.endswith(".json"):
            report_p = os.path.join(root, f)
            break

if report_p and os.path.exists(report_p):
    print(f"\n讀取報告: {report_p}")
    with open(report_p, "r", encoding="utf-8") as f:
        d = json.load(f)
    mmap = d.get("measure_map", [])
    print(f"Total measures: {len(mmap)}")
    if mmap:
        times = [m["start_time"] for m in mmap]
        diffs = np.diff(times)
        bpms = 60.0 / (diffs / 4.0)
        print(f"Time range: {times[0]:.3f}s ~ {mmap[-1]['end_time']:.3f}s")
        print(f"Interval median: {np.median(diffs):.4f}s (BPM median: {np.median(bpms):.2f})")
        print(f"Interval min: {np.min(diffs):.4f}s, max: {np.max(diffs):.4f}s, std: {np.std(diffs):.4f}s")

        print("\n前 10 個小節明細:")
        for m in mmap[:10]:
            st = m.get("start_time", 0.0)
            et = m.get("end_time", 0.0)
            dur = et - st
            bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
            print(f"Measure {m.get('measure'):2d}: {st:6.3f}s ~ {et:6.3f}s | Duration: {dur:5.3f}s | BPM: {bpm:5.1f}")
