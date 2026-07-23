"""
PGMCraft Behavior Tree Workflow Builder & FSM Runner.
"""

from pgm_craft.workflow.nodes import SequenceNode, FallbackNode, ParallelNode, Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import (
    VideoURLDownloadNode,
    AudioLoadNode,
    DemucsStemNode,
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
    HybridPitchNode
)

def build_pgm_workflow_tree():
    """
    Constructs the Behavior Tree (BT) for PGMCraft Workflow:

    Sequence [Root]
    ├── VideoURLDownloadNode
    ├── AudioLoadNode
    ├── DemucsStemNode
    ├── Fallback [BeatTrackingSelector]
    │   ├── BeatNetNode
    │   └── LibrosaBeatNode (Fallback)
    ├── BeatValidationNode
    ├── DownbeatRefineNode
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
    └── HybridPitchNode                 ← 依賴 CREPE 輸出，保持順序
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
        VideoURLDownloadNode(),
        AudioLoadNode(),
        DemucsStemNode(),
        beat_tracking_fallback,
        BeatValidationNode(),
        DownbeatRefineNode(),
        MeasureMapNode(),
        SectionStructureNode(),
        KeyChordAnalysisNode(),
        ClickSynthesisNode(),
        MIDIExportNode(),
        ai_parallel_group,
        HybridPitchNode(),        # 依賴 CREPEPitchNode 的 pitch_contour，在 Parallel 後執行
    ])

    return root_sequence









class BTWorkflowEngine:
    """Behavior Tree Engine wrapper for running audio pipelines."""
    def __init__(self):
        self.tree = build_pgm_workflow_tree()

    def run(self, audio_path, output_dir="outputs", enable_stem=False, validate_contracts=False):
        blackboard = Blackboard()
        blackboard.set_val("audio_path", audio_path)
        blackboard.set_val("output_dir", output_dir)
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
