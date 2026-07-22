"""
PGMCraft Main Engine Pipeline (Behavior Tree & FSM Powered)
Unified orchestrator for Stem Separation, Music Analysis & PGM Click/MIDI Export.
"""

import os
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from pgm_craft.workflow.builder import BTWorkflowEngine

class PGMCraftEngine:
    def __init__(self, enable_stem_separation=False):
        self.enable_stem_separation = enable_stem_separation
        self.bt_engine = BTWorkflowEngine()

    def run(self, audio_path, output_dir="outputs"):
        os.makedirs(output_dir, exist_ok=True)
        
        # Run Behavior Tree Workflow Engine
        blackboard = self.bt_engine.run(
            audio_path=audio_path,
            output_dir=output_dir,
            enable_stem=self.enable_stem_separation
        )

        original_beats = blackboard.get_val("beats")
        beats = blackboard.get_val("refined_beats", original_beats)
        estimated_key = blackboard.get_val("estimated_key", "C Major")
        chords = blackboard.get_val("chord_progression", [])
        stems = blackboard.get_val("stems", {})
        beat_validation = blackboard.get_val("beat_validation", {})
        downbeat_refinement = blackboard.get_val("downbeat_refinement", {})
        measure_map = blackboard.get_val("measure_map", [])
        measure_map_status = blackboard.get_val("measure_map_status", "UNKNOWN")
        measure_map_warnings = blackboard.get_val("measure_map_warnings", [])

        # Calculate BPM stats & measures
        diffs = np.diff(beats[:, 0]) if beats is not None else np.array([0.5])
        bpms = 60.0 / diffs if len(diffs) > 0 else np.array([120.0])
        avg_bpm = float(np.mean(bpms)) if len(bpms) > 0 else 120.0
        min_bpm = float(np.min(bpms)) if len(bpms) > 0 else 120.0
        max_bpm = float(np.max(bpms)) if len(bpms) > 0 else 120.0

        downbeat_count = sum(1 for b in beats if int(b[1]) == 1) if beats is not None else 0

        # Generate Tempo Curve Plot
        fig, ax = plt.subplots(figsize=(10, 4))
        if beats is not None and len(beats) > 1:
            ax.plot(beats[:-1, 0], bpms, color='#4F46E5', linewidth=1.8, label='Dynamic BPM')
        ax.axhline(avg_bpm, color='#EF4444', linestyle='--', label=f'Avg BPM ({avg_bpm:.1f})')
        ax.set_title("PGMCraft BT Workflow Dynamic Tempo Profile")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("BPM")
        ax.grid(True, alpha=0.3)
        ax.legend()

        plot_path = os.path.join(output_dir, "tempo_curve.png")
        plt.tight_layout()
        plt.savefig(plot_path, dpi=150)
        plt.close()

        report = {
            "audio_file": audio_path,
            "estimated_key": estimated_key,
            "average_bpm": round(avg_bpm, 1),
            "min_bpm": round(min_bpm, 1),
            "max_bpm": round(max_bpm, 1),
            "total_beats": len(beats) if beats is not None else 0,
            "total_measures": len(measure_map) if measure_map else (downbeat_count if downbeat_count > 0 else (len(beats) // 4 if beats is not None else 0)),
            "beat_validation": beat_validation,
            "downbeat_refinement": downbeat_refinement,
            "measure_map_status": measure_map_status,
            "measure_map_warnings": measure_map_warnings,
            "measure_map": measure_map,
            "chord_progression": chords,
            "stems": stems,
            "outputs": {
                "click_track": blackboard.get_val("click_track"),
                "mix_with_click": blackboard.get_val("mix_with_click"),
                "tempo_map_midi": blackboard.get_val("tempo_map_midi"),
                "click_guide_midi": blackboard.get_val("click_guide_midi"),
                "tempo_curve_plot": plot_path
            }
        }

        # Write JSON metadata report
        with open(os.path.join(output_dir, "pgm_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report
