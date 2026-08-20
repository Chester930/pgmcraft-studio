"""
追查 MeasureMapNode build_measure_map() 接收到的 refined_beats/beats 的 Downbeat 索引
"""

import os
import json
import glob
import numpy as np

# 直接還原 reverify_report 中記錄的度量
report_path = r"outputs/pass190_default_pipeline_reverify/reverify_report.json"
if os.path.exists(report_path):
    with open(report_path, encoding="utf-8") as f:
        rep = json.load(f)
    print("reverify report:", rep.get("stats"))
