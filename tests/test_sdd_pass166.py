"""
SDD Pass 166 — 清理孤立死路徑 Tree A (build_module3_barstart_v2_pipeline_tree) 委派化與相容性驗證

背景：
原本的 `build_module3_barstart_v2_pipeline_tree()` (Tree A) 繞過了 Stage 3 Beat Tracking，無法讀取 Stage 3 BeatNet 與 v1 網格資料。Pass 166 將其簡化為向下委派呼叫包含完整 Stage 3 數據的主樹 `build_module3_pipeline_tree()`。

本測試驗證：
1. `build_module3_barstart_v2_pipeline_tree()` 能正常被調用並回傳合法的 BT 樹節點。
2. `builder.py` 的 `build_master_pipeline_tree(target_stage="module3_barstart_v2")` 依然維持向下相容運作。
"""

import pytest

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import build_module3_barstart_v2_pipeline_tree
from pgm_craft.workflow.nodes import BaseNode


class TestSDDPass166:

    def test_tree_a_delegates_to_valid_bt_node(self):
        tree = build_module3_barstart_v2_pipeline_tree()
        assert isinstance(tree, BaseNode)

    def test_builder_target_stage_module3_barstart_v2_backward_compatibility(self):
        tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
        assert isinstance(tree, BaseNode)
