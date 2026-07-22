"""
PGMCraft Behavior Tree Workflow Builder & FSM Runner.
"""

from pgm_craft.workflow.nodes import SequenceNode, FallbackNode, Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import (
    VideoURLDownloadNode,
    AudioLoadNode,
    DemucsStemNode,
    BeatNetNode,
    LibrosaBeatNode,
    BeatValidationNode,
    MeasureMapNode,
    KeyChordAnalysisNode,
    ClickSynthesisNode,
    MIDIExportNode
)

def build_pgm_workflow_tree():
    """
    Constructs the Behavior Tree (BT) for PGMCraft Workflow:
    
    Sequence [Root]
    ├── VideoURLDownloadNode (1st Node: Auto Download URL if input is URL)
    ├── AudioLoadNode        (2nd Node: Load Audio PCM Data)
    ├── DemucsStemNode       (3rd Node: Optional Stem Separation)
    ├── Fallback [BeatTrackingSelector]
    │   ├── BeatNetNode
    │   └── LibrosaBeatNode (Fallback)
    ├── BeatValidationNode
    ├── MeasureMapNode
    ├── KeyChordAnalysisNode
    ├── ClickSynthesisNode
    └── MIDIExportNode
    """
    beat_tracking_fallback = FallbackNode("BeatTrackingSelector", [
        BeatNetNode(),
        LibrosaBeatNode()
    ])

    root_sequence = SequenceNode("PGMCraftWorkflowRoot", [
        VideoURLDownloadNode(),
        AudioLoadNode(),
        DemucsStemNode(),
        beat_tracking_fallback,
        BeatValidationNode(),
        MeasureMapNode(),
        KeyChordAnalysisNode(),
        ClickSynthesisNode(),
        MIDIExportNode()
    ])

    return root_sequence


class BTWorkflowEngine:
    """Behavior Tree Engine wrapper for running audio pipelines."""
    def __init__(self):
        self.tree = build_pgm_workflow_tree()

    def run(self, audio_path, output_dir="outputs", enable_stem=False):
        blackboard = Blackboard()
        blackboard.set_val("audio_path", audio_path)
        blackboard.set_val("output_dir", output_dir)
        blackboard.set_val("enable_stem", enable_stem)

        print(f"\n=== [BT Engine] Executing Behavior Tree Workflow for {audio_path} ===")
        status = self.tree.execute(blackboard)

        if status == NodeStatus.SUCCESS:
            print("=== [BT Engine] Behavior Tree Execution Finished Successfully! ===")
        else:
            print("=== [BT Engine] Behavior Tree Execution Failed! ===")

        return blackboard
