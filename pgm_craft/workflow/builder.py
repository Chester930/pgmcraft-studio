"""
PGMCraft Behavior Tree Workflow Builder & FSM Runner.
"""

from pgm_craft.workflow.nodes import SequenceNode, ParallelNode, Blackboard, NodeStatus
from pgm_craft.workflow.input_acquisition_bt import build_input_acquisition_tree
from pgm_craft.workflow.audio_quality_bt import build_audio_quality_tree
from pgm_craft.workflow.stem_separation_bt import build_stem_separation_tree
from pgm_craft.workflow.beat_tracking_bt import build_beat_tracking_tree
from pgm_craft.workflow.music_analysis_bt import build_music_analysis_tree

from pgm_craft.workflow.audio_nodes import (
    ClickSynthesisNode,
    MIDIExportNode,
    BasicPitchNode,
    CREPEPitchNode,
    PodcastSpeechNode,
    InstrumentPresenceNode,
    HybridPitchNode,
    AudioQuantizerNode,
    MIDIQuantizerGuardNode,
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
    - Stage 5~6: DAW Export & Packaging
    """
    # 四個 AI 分析節點彼此獨立，可安全並行
    ai_parallel_group = ParallelNode("AIAnalysisGroup", children=[
        BasicPitchNode(),
        CREPEPitchNode(),
        InstrumentPresenceNode(),
        PodcastSpeechNode(),
    ], success_threshold=1)   # 至少有一個成功即繼續（含 graceful fallback 節點）

    root_sequence = SequenceNode("PGMCraftWorkflowRoot", [
        build_input_acquisition_tree(),  # Stage 0: 下載/驗證 + 專案資料夾建立
        build_audio_quality_tree(),     # Stage 1: 載入 + 11項品質評估 + 去雜訊人群 + 正規化
        build_stem_separation_tree(),   # Stage 2: 需求驅動樂器分軌
        build_beat_tracking_tree(),      # Stage 3: 雙軌併行節拍分析與動態融合
        build_music_analysis_tree(),     # Stage 4: 和聲專屬 Sub-mix 與調性/和弦/段落分析
        AudioQuantizerNode(),
        ClickSynthesisNode(),
        MIDIExportNode(),
        ai_parallel_group,
        HybridPitchNode(),        # 依賴 CREPEPitchNode 的 pitch_contour，在 Parallel 後執行
        MIDIQuantizerGuardNode(),
        VoiceSplitMIDIExportNode(),
    ])

    return root_sequence


def build_master_pipeline_tree():
    """
    Constructs the Master Behavior Tree (Master Pipeline Engine) incorporating:
    - Stage 0: Input Acquisition (Download / Local Passthrough & Project Setup)
    - Stage 1: Audio Quality & Crowd/Environmental Noise Discard
    - Stage 2: Stem Separation Tree (Vocals, Drums, Bass, Guitar)
    - Stage 3: Beat Tracking Tree (Dual-Track Parallel & Dynamic Fusion)
    - Stage 4: Music Analysis Tree (Harmonic Sub-Mix & Key-Chord Analysis)
    - Stage 5~6: DAW Export & Packaging
    """
    ai_parallel_group = ParallelNode("AIAnalysisGroup", children=[
        BasicPitchNode(),
        CREPEPitchNode(),
        InstrumentPresenceNode(),
        PodcastSpeechNode(),
    ], success_threshold=1)

    master_sequence = SequenceNode("MasterPipelineTree", [
        build_input_acquisition_tree(),
        build_audio_quality_tree(),
        build_stem_separation_tree(),
        build_beat_tracking_tree(),
        build_music_analysis_tree(),
        AudioQuantizerNode(),
        ClickSynthesisNode(),
        MIDIExportNode(),
        ai_parallel_group,
        HybridPitchNode(),
        MIDIQuantizerGuardNode(),
        VoiceSplitMIDIExportNode(),
    ])

    return master_sequence


def build_pgm_workflow_tree():
    return build_full_pipeline_tree()


class BTWorkflowEngine:
    """Behavior Tree Engine wrapper for running audio pipelines."""
    def __init__(self):
        self.tree = build_full_pipeline_tree()

    def run(self, audio_path, output_dir="outputs", enable_stem=False, validate_contracts=False):
        blackboard = Blackboard()
        blackboard.set_val("audio_path", audio_path)
        blackboard.set_val("output_dir", output_dir)
        blackboard.set_val("project_root", output_dir)  # Stage 0 ValidateProjectRootNode 需要
        blackboard.set_val("enable_stem", enable_stem)
        blackboard.set_val("validate_contracts", validate_contracts)

        print(f"\n=== [BT Engine] Executing Behavior Tree Workflow for {audio_path} ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("workflow_status", status.name)

        if status == NodeStatus.SUCCESS:
            print("=== [BT Engine] Behavior Tree Execution Finished Successfully! ===")
        else:
            print("=== [BT Engine] Behavior Tree Execution Failed! ===")

        return blackboard


# 為向下相容測試別名導出
MasterBTWorkflowEngine = BTWorkflowEngine

