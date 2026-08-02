"""
tests/test_beat_stem_tree.py

SDD 驗收測試：beat-stem-optimization
測試對象：
  - build_beat_stem_tree() 可以 import 與 instantiate
  - OptionalStemSeparationNode(mode='beat_only') 使用輕量樹
  - OptionalStemSeparationNode(mode='full') 使用完整樹（不影響全自動流程）
  - ChordMelodyOnsetSplitNode 仍存在於 beat_only 下游鏈（BarStartV2CoreChain）
"""
import pytest


# ---------------------------------------------------------------------------
# Task 1 驗收：build_beat_stem_tree() import 與 instantiate
# ---------------------------------------------------------------------------

def test_build_beat_stem_tree_importable():
    from pgm_craft.workflow.stem_separation_bt import build_beat_stem_tree
    assert callable(build_beat_stem_tree)


def test_build_beat_stem_tree_returns_node():
    from pgm_craft.workflow.stem_separation_bt import build_beat_stem_tree
    from pgm_craft.workflow.bt_core import BaseNode
    tree = build_beat_stem_tree()
    assert isinstance(tree, BaseNode)


def test_build_beat_stem_tree_root_name():
    from pgm_craft.workflow.stem_separation_bt import build_beat_stem_tree
    tree = build_beat_stem_tree()
    assert tree.name == "BeatAnalysisStemRoot"


def test_build_beat_stem_tree_contains_expected_branches():
    """確認輕量樹包含 Vocals / Drums / Bass / GuitarPiano 四條分支。"""
    from pgm_craft.workflow.stem_separation_bt import build_beat_stem_tree
    tree = build_beat_stem_tree()
    child_names = [c.name for c in tree.children]
    for expected in [
        "EnsureStemsFolderNode",
        "BeatStemVocalsFallback",
        "BeatStemDrumsFallback",
        "BeatStemBassFallback",
        "BeatStemGuitarPianoFallback",
        "StrictStemDirectoryGuardNode",
        "RegisterStemsToBlackboardNode",
    ]:
        assert expected in child_names, f"Missing child: {expected}"


# ---------------------------------------------------------------------------
# Task 2 驗收：OptionalStemSeparationNode mode 參數
# ---------------------------------------------------------------------------

def test_optional_stem_separation_node_default_is_full_tree():
    """預設 mode='full' → 使用 build_stem_separation_tree()，根節點名稱應不同於 BeatAnalysisStemRoot。"""
    from pgm_craft.workflow.module3_bt import OptionalStemSeparationNode
    node = OptionalStemSeparationNode()  # mode='full' 預設
    assert node.tree.name != "BeatAnalysisStemRoot"


def test_optional_stem_separation_node_beat_only_uses_light_tree():
    """mode='beat_only' → 使用 build_beat_stem_tree()，根節點名稱應為 BeatAnalysisStemRoot。"""
    from pgm_craft.workflow.module3_bt import OptionalStemSeparationNode
    node = OptionalStemSeparationNode(mode="beat_only")
    assert node.tree.name == "BeatAnalysisStemRoot"


def test_optional_stem_separation_node_explicit_full():
    from pgm_craft.workflow.module3_bt import OptionalStemSeparationNode
    node_default = OptionalStemSeparationNode()
    node_full = OptionalStemSeparationNode(mode="full")
    assert node_default.tree.name == node_full.tree.name


# ---------------------------------------------------------------------------
# Task 3 驗收：module3_barstart_v2_pipeline_tree 使用 beat_only
# ---------------------------------------------------------------------------

def test_module3_barstart_v2_pipeline_uses_beat_only():
    """build_module3_barstart_v2_pipeline_tree 中的 OptionalStemSeparationNode 應為輕量樹。"""
    from pgm_craft.workflow.module3_barstart_v2_bt import build_module3_barstart_v2_pipeline_tree
    from pgm_craft.workflow.module3_bt import OptionalStemSeparationNode

    tree = build_module3_barstart_v2_pipeline_tree()

    # 遞迴搜尋樹中所有 OptionalStemSeparationNode
    def find_nodes(node, cls):
        found = []
        if isinstance(node, cls):
            found.append(node)
        if hasattr(node, "children"):
            for c in node.children:
                found.extend(find_nodes(c, cls))
        return found

    sep_nodes = find_nodes(tree, OptionalStemSeparationNode)
    assert len(sep_nodes) >= 1, "找不到 OptionalStemSeparationNode"
    for n in sep_nodes:
        assert n.tree.name == "BeatAnalysisStemRoot", (
            f"module3_barstart_v2_pipeline_tree 內的 OptionalStemSeparationNode"
            f" 應使用輕量樹，但根節點為 '{n.tree.name}'"
        )


# ---------------------------------------------------------------------------
# ChordMelodyOnsetSplitNode 仍在 BarStartV2CoreChain（beat_only 下游）
# ---------------------------------------------------------------------------

def test_chord_melody_onset_split_node_in_barstart_v2_chain():
    """_run_barstart_v2_comparison 產生的 BarStartV2CoreChain 仍包含 ChordMelodyOnsetSplitNode。"""
    from pgm_craft.workflow.module3_bt import _run_barstart_v2_comparison
    from pgm_craft.workflow.module3_barstart_v2_bt import ChordMelodyOnsetSplitNode
    from pgm_craft.core.blackboard import Blackboard

    bb = Blackboard()
    chain = _run_barstart_v2_comparison(bb)  # 應回傳 SequenceNode

    def find_nodes(node, cls):
        found = []
        if isinstance(node, cls):
            found.append(node)
        if hasattr(node, "children"):
            for c in node.children:
                found.extend(find_nodes(c, cls))
        return found

    results = find_nodes(chain, ChordMelodyOnsetSplitNode)
    assert len(results) >= 1, "ChordMelodyOnsetSplitNode 應在 BarStartV2CoreChain 中"


# ---------------------------------------------------------------------------
# 全自動流程回歸：BarStartV2AutoMergeNode 仍可 instantiate
# ---------------------------------------------------------------------------

def test_barstart_v2_auto_merge_node_instantiates():
    from pgm_craft.workflow.module3_bt import BarStartV2AutoMergeNode
    node = BarStartV2AutoMergeNode()
    assert node is not None