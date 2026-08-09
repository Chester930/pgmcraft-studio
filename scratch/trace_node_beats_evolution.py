"""
追查 Stage 3 每個 BT Node 執行前後 beats 陣列標號演變
"""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.workflow.nodes import Blackboard

# 模擬跑小範例測試看 beats 的 152.022s 處在各 Node 的變化
def main():
    pass

if __name__ == "__main__":
    main()
