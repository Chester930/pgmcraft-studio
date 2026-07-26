"""
PGMCraft Behavior Tree Workflow Builder & FSM Runner.
"""

from pgm_craft.workflow.nodes import SequenceNode, FallbackNode, ParallelNode, Blackboard, NodeStatus
from pgm_craft.workflow.input_acquisition_bt import build_input_acquisition_tree
from pgm_craft.workflow.audio_quality_bt import build_audio_quality_tree
from pgm_craft.workflow.stem_separation_bt import build_stem_separation_tree

from pgm_craft.workflow.audio_nodes import (
    SubMixGeneratorNode,
    BeatNetNode,
    LibrosaBeatNode,
    BeatValidationNode,
    DownbeatRefineNode,
    MeasureMapNode,
    SectionStructureNode,
    KeyChordAnalysisNode,
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

def build_pgm_workflow_tree():
    """
    Constructs the Behavior Tree (BT) for PGMCraft Workflow:

    Sequence [Root]
    ├── VideoURLDownloadNode
    ├── AudioLoadNode
    ├── DemucsStemNode
    ├── SubMixGeneratorNode            ← 合成專屬 Sub-Mix 音軌 (Drums+Bass / Guitar+Piano / Vocals+Drums)
    ├── Fallback [BeatTrackingSelector]
    │   ├── BeatNetNode
    │   └── LibrosaBeatNode (Fallback)
    ├── BeatValidationNode
    ├── DownbeatRefineNode
    ├── AudioQuantizerNode              ← 音訊格點與 Offset 自動對齊量化
    ├── MeasureMapNode
    ├── SectionStructureNode
    ├── KeyChordAnalysisNode
    ├── ClickSynthesisNode
    ├── MIDIExportNode
    ├── Parallel [AIAnalysisGroup]      ← 並行執行 AI 密集型節點
    │   ├── BasicPitchNode
    │   ├── CREPEPitchNode
    │   ├── InstrumentPresenceNode
    │   └── PodcastSpeechNode
    ├── HybridPitchNode                 ← 依賴 CREPE 輸出，保持順序
    ├── MIDIQuantizerGuardNode          ← MIDI 網格量化與搖擺感修復衛兵
    └── VoiceSplitMIDIExportNode        ← 鋼琴/吉他專屬雙手與音域 MIDI 拆分
    """
    beat_tracking_fallback = FallbackNode("BeatTrackingSelector", [
        BeatNetNode(),
        LibrosaBeatNode()
    ])

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
        SubMixGeneratorNode(),
        beat_tracking_fallback,
        BeatValidationNode(),
        DownbeatRefineNode(),
        AudioQuantizerNode(),
        MeasureMapNode(),
        SectionStructureNode(),
        KeyChordAnalysisNode(),
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
    - Stage 3~6: Beat Tracking, Music Analysis, DAW Export
    """
    beat_tracking_fallback = FallbackNode("BeatTrackingSelector", [
        BeatNetNode(),
        LibrosaBeatNode()
    ])

    ai_parallel_group = ParallelNode("AIAnalysisGroup", children=[
        BasicPitchNode(),
        CREPEPitchNode(),
        InstrumentPresenceNode(),
        PodcastSpeechNode(),
    ], success_threshold=1)

    master_sequence = SequenceNode("MasterPGMPipelineRoot", [
        build_input_acquisition_tree(),
        build_audio_quality_tree(),
        build_stem_separation_tree(),
        SubMixGeneratorNode(),
        beat_tracking_fallback,
        BeatValidationNode(),
        DownbeatRefineNode(),
        AudioQuantizerNode(),
        MeasureMapNode(),
        SectionStructureNode(),
        KeyChordAnalysisNode(),
        ClickSynthesisNode(),
        MIDIExportNode(),
        ai_parallel_group,
        HybridPitchNode(),
        MIDIQuantizerGuardNode(),
        VoiceSplitMIDIExportNode(),
    ])

    return master_sequence


class BTWorkflowEngine:
    """Behavior Tree Engine wrapper for running audio pipelines."""
    def __init__(self):
        self.tree = build_pgm_workflow_tree()

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


class MasterBTWorkflowEngine(BTWorkflowEngine):
    """Engine wrapper for running the Master Pipeline Behavior Tree."""
    def __init__(self):
        super().__init__()
        self.tree = build_master_pipeline_tree()

    def run_master_pipeline(self, audio_path, output_dir="outputs", validate_contracts=True):
        return self.run(audio_path=audio_path, output_dir=output_dir, enable_stem=True, validate_contracts=validate_contracts)
