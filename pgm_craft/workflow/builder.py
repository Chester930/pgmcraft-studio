"""
PGMCraft Behavior Tree Workflow Builder & FSM Runner.
"""

from pgm_craft.workflow.nodes import SequenceNode, ParallelNode, Blackboard, NodeStatus
from pgm_craft.workflow.input_acquisition_bt import build_input_acquisition_tree
from pgm_craft.workflow.audio_quality_bt import build_audio_quality_tree
from pgm_craft.workflow.stem_separation_bt import build_stem_separation_tree
from pgm_craft.workflow.beat_tracking_bt import build_beat_tracking_tree
from pgm_craft.workflow.music_analysis_bt import build_music_analysis_tree
from pgm_craft.workflow.export_bt import build_export_tree
from pgm_craft.workflow.package_bt import build_package_tree
from pgm_craft.workflow.module3_bt import build_module3_pipeline_tree, BarStartV2AutoMergeNode
from pgm_craft.workflow.module3_barstart_v2_bt import build_module3_barstart_v2_pipeline_tree

from pgm_craft.workflow.audio_nodes import (
    BasicPitchNode,
    CREPEPitchNode,
    PodcastSpeechNode,
    InstrumentPresenceNode,
    HybridPitchNode,
    VoiceSplitMIDIExportNode
)

def build_full_pipeline_tree():
    """
    Constructs the Master Behavior Tree incorporating:
    - Stage 0: Input Acquisition (Download / Local Passthrough & Project Setup)
    - Stage 1: Audio Quality & Crowd/Environmental Noise Discard
    - Stage 2: Stem Separation Tree (Vocals, Drums, Bass, Guitar)
    - Stage 3: Beat Tracking Tree (Dual-Track Parallel & Dynamic Fusion)
    - Stage 4: Music Analysis Tree (Harmonic Sub-Mix & Key-Chord Analysis)
    - Stage 5: Export Tree (Click, MIDI, Marker Section Export)
    - Stage 6: Package Tree (DAW Session Projects, Live Dashboard & ZIP Archive)
    """
    ai_parallel_group = ParallelNode("AIAnalysisGroup", children=[
        BasicPitchNode(),
        CREPEPitchNode(),
        InstrumentPresenceNode(),
        PodcastSpeechNode(),
    ], success_threshold=1)   # 至少有一個成功即繼續（含 graceful fallback 節點）

    root_sequence = SequenceNode("PGMFullPipelineRoot", [
        build_input_acquisition_tree(),  # Stage 0: 下載/驗證 + 專案資料夾建立
        build_audio_quality_tree(),     # Stage 1: 載入 + 11項品質評估 + 去雜訊人群 + 正規化
        build_stem_separation_tree(),   # Stage 2: 需求驅動樂器分軌
        build_beat_tracking_tree(),      # Stage 3: 雙軌併行節拍分析與動態融合
        BarStartV2AutoMergeNode(),       # 誠實 v1/v2 自動分數閘門合併（無需人工驗收）
        build_music_analysis_tree(),     # Stage 4: 和聲專屬 Sub-mix 與調性/和弦/段落分析
        build_export_tree(),             # Stage 5: Click, MIDI, DAW Section Markers 素材導出
        ai_parallel_group,
        HybridPitchNode(),        # 依賴 CREPEPitchNode 的 pitch_contour，在 Parallel 後執行
        VoiceSplitMIDIExportNode(),
        build_package_tree(), # Stage 6
    ])

    return root_sequence


def build_master_pipeline_tree(target_stage: str = "full"):
    """
    Constructs the Master Behavior Tree dynamically truncating at target_stage.
    target_stage options: 'stage1', 'stage2', 'stage3', 'stage4', 'stage5', 'stage6', 'module3', 'module3_barstart_v2', 'full'
    """
    if target_stage == "module3":
        return build_module3_pipeline_tree()
    if target_stage == "module3_barstart_v2":
        return build_module3_barstart_v2_pipeline_tree()

    stage_nodes = [
        build_input_acquisition_tree(), # Stage 0
        build_audio_quality_tree(),      # Stage 1
    ]

    if target_stage == "stage1":
        return SequenceNode("MasterPGMPipelineRoot_Stage1", stage_nodes)

    stage_nodes.append(build_stem_separation_tree()) # Stage 2
    if target_stage == "stage2":
        return SequenceNode("MasterPGMPipelineRoot_Stage2", stage_nodes)

    stage_nodes.append(build_beat_tracking_tree()) # Stage 3
    if target_stage == "stage3":
        return SequenceNode("MasterPGMPipelineRoot_Stage3", stage_nodes)

    stage_nodes.append(BarStartV2AutoMergeNode())  # 誠實 v1/v2 自動分數閘門合併（無需人工驗收）
    stage_nodes.append(build_music_analysis_tree()) # Stage 4
    if target_stage == "stage4":
        return SequenceNode("MasterPGMPipelineRoot_Stage4", stage_nodes)

    ai_parallel_group = ParallelNode("AIAnalysisGroup", children=[
        BasicPitchNode(),
        CREPEPitchNode(),
        InstrumentPresenceNode(),
        PodcastSpeechNode(),
    ], success_threshold=1)

    stage_nodes.extend([
        build_export_tree(), # Stage 5
        ai_parallel_group,
        HybridPitchNode(),
        VoiceSplitMIDIExportNode(),
    ])
    if target_stage == "stage5":
        return SequenceNode("MasterPGMPipelineRoot_Stage5", stage_nodes)

    stage_nodes.append(build_package_tree()) # Stage 6

    return SequenceNode("MasterPGMPipelineRoot", stage_nodes)


def build_pgm_workflow_tree():
    return build_full_pipeline_tree()


class BTWorkflowEngine:
    """Behavior Tree Engine wrapper for running audio pipelines."""
    def __init__(self, target_stage: str = "full"):
        self.target_stage = target_stage
        self.tree = build_master_pipeline_tree(target_stage=target_stage)

    def run(
        self,
        audio_path,
        output_dir="outputs",
        enable_stem=False,
        validate_contracts=False,
        target_stage: str = None,
        module3_candidate_sources=None,
        manual_bar_starts=None,
        user_meter_selection=None,
        allow_temporary_bar_delta=None,
        barstart_v2_postprocess_flags=None,
    ):
        if target_stage is not None and target_stage != self.target_stage:
            self.target_stage = target_stage
            self.tree = build_master_pipeline_tree(target_stage=target_stage)

        blackboard = Blackboard()
        blackboard.set_val("audio_path", audio_path)
        blackboard.set_val("output_dir", output_dir)
        blackboard.set_val("project_root", output_dir)  # Stage 0 ValidateProjectRootNode 需要
        blackboard.set_val("enable_stem", enable_stem)
        blackboard.set_val("validate_contracts", validate_contracts)
        blackboard.set_val("target_stage", self.target_stage)
        if module3_candidate_sources is not None:
            blackboard.set_val("module3_candidate_sources", module3_candidate_sources)
        if manual_bar_starts is not None:
            blackboard.set_val("manual_bar_starts", manual_bar_starts)
        if user_meter_selection is not None:
            blackboard.set_val("user_meter_selection", user_meter_selection)
        if allow_temporary_bar_delta is not None:
            blackboard.set_val("allow_temporary_bar_delta", allow_temporary_bar_delta)
        if barstart_v2_postprocess_flags is not None:
            # Pass 171: 讓多版本比較 harness 能獨立開關 Pass 168/169/170 後處理節點
            blackboard.set_val("barstart_v2_postprocess_flags", barstart_v2_postprocess_flags)

        print(f"\n=== [BT Engine] Executing Behavior Tree Workflow (Target: {self.target_stage}) for {audio_path} ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("workflow_status", status.name)

        if status == NodeStatus.SUCCESS:
            print("=== [BT Engine] Behavior Tree Execution Finished Successfully! ===")
        else:
            print("=== [BT Engine] Behavior Tree Execution Failed! ===")

        return blackboard


# 為向下相容測試別名導出
MasterBTWorkflowEngine = BTWorkflowEngine
