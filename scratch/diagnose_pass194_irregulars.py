"""
Pass 194 診斷：追查 10 個不規則小節，是否落在 SteadyPercussionCountAnchorNode
建立的保護區段邊界附近，還是別的原因。
"""

import os
import sys
import json
import glob

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode
from pgm_craft.workflow.nodes import Blackboard

REPORT_PATH = glob.glob(r"outputs/pass194_default_pipeline_reverify/**/measure_map.json", recursive=True)[0]
STEMS_DIR = r"outputs\pass194_default_pipeline_reverify\_shared_stems_cache\stems"

with open(REPORT_PATH, encoding="utf-8") as f:
    data = json.load(f)
m_map = data["measure_map"]
print(f"總小節數：{len(m_map)}")

irregulars = [m for m in m_map if m.get("is_variable_length")]
print(f"不規則小節數：{len(irregulars)}\n")

for m in irregulars:
    idx = m["measure"] - 1
    prev_m = m_map[idx - 1] if idx > 0 else None
    next_m = m_map[idx + 1] if idx + 1 < len(m_map) else None
    print(f"==== 不規則小節 #{m['measure']}: beat_count={m['beat_count']}, start={m['start_time']:.3f}s ====")
    if prev_m:
        print(f"  前一小節 #{prev_m['measure']}: beat_count={prev_m['beat_count']}, "
              f"beats={[(b['beat'], round(b['time'],3)) for b in prev_m['beats']]}")
    print(f"  本小節 beats={[(b['beat'], round(b['time'],3)) for b in m['beats']]}")
    if next_m:
        print(f"  後一小節 #{next_m['measure']}: beat_count={next_m['beat_count']}, "
              f"beats={[(b['beat'], round(b['time'],3)) for b in next_m['beats']]}")
    print()

# 重建 beats 陣列，重跑 SteadyPercussionCountAnchorNode 取得這次真實跑法
# 應該產生的 beat_phase_protected_ranges，核對 9 個問題點是不是都落在
# 保護區段邊界附近。
rows = []
for m in m_map:
    for b in m["beats"]:
        rows.append((b["time"], b["beat"]))
rows.sort(key=lambda r: r[0])
beats = np.array(rows, dtype=float)

bb = Blackboard()
bb.set_val("beats", beats)
bb.set_val("stems", {})
bb.set_val("stems_dir", STEMS_DIR)

node = SteadyPercussionCountAnchorNode()
node.execute(bb)
protected = bb.get_val("beat_phase_protected_ranges", [])
print(f"\n重跑後保護區段數量：{len(protected)}")
for p in protected:
    print(f"  {p[0]:.3f}s - {p[1]:.3f}s")

print("\n核對 9 個問題點是否落在保護區段邊界附近（±1 拍距 0.4s）：")
for m in irregulars:
    t = m["start_time"]
    nearest = None
    nearest_dist = None
    for p_start, p_end in protected:
        for edge in (p_start, p_end):
            d = abs(t - edge)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest = edge
    flag = "✅ 邊界附近" if nearest_dist is not None and nearest_dist <= 0.4 else "❌ 不是邊界"
    print(f"  measure start={t:.3f}s -> 最近保護邊界={nearest:.3f}s (差 {nearest_dist:.3f}s) {flag}")
