import os
import json

out_dir = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\comparison_test_pass168"
report_p = None
for root, dirs, files in os.walk(out_dir):
    for f in files:
        if f == "measure_map.json":
            report_p = os.path.join(root, f)
            break

if report_p and os.path.exists(report_p):
    with open(report_p, "r", encoding="utf-8") as f:
        mmap = json.load(f)
    if isinstance(mmap, dict):
        mmap = mmap.get("measure_map", [])

    print("=== Pass 168 雙向確信錨點反推修復後：前奏區段 (0s~32s) ===")
    measures_span1 = [m for m in mmap if 0.0 <= m.get("start_time", 0) <= 32.0]
    for m in measures_span1:
        st = m.get("start_time", 0)
        et = m.get("end_time", 0)
        dur = et - st
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  M{m.get('measure'):3d}: {st:6.3f}s ~ {et:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")

    print("\n=== Pass 168 雙向確信錨點反推修復後：間奏區段 (95s~125s) ===")
    measures_span2 = [m for m in mmap if 95.0 <= m.get("start_time", 0) <= 125.0]
    for m in measures_span2:
        st = m.get("start_time", 0)
        et = m.get("end_time", 0)
        dur = et - st
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  M{m.get('measure'):3d}: {st:6.3f}s ~ {et:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")
