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
from pgm_craft.packager import PGMProjectPackager

class PGMCraftEngine:
    def __init__(self, enable_stem_separation=False, validate_contracts=False):
        self.enable_stem_separation = enable_stem_separation
        self.validate_contracts = validate_contracts
        self.bt_engine = BTWorkflowEngine()
        self.packager = PGMProjectPackager()

    def run(self, audio_path, output_dir="outputs"):
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"[BT Broadcaster] 啟動 Behavior Tree 即時廣播與節點執行追蹤: {os.path.basename(audio_path)}")

        # Run Behavior Tree Workflow Engine
        blackboard = self.bt_engine.run(
            audio_path=audio_path,
            output_dir=output_dir,
            enable_stem=self.enable_stem_separation,
            validate_contracts=self.validate_contracts,
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
        workflow_status = blackboard.get_val("workflow_status", "UNKNOWN")
        workflow_trace = blackboard.get_val("workflow_trace", [])
        contract_validation = blackboard.get_val("contract_validation", [])

        # Calculate BPM stats, measures & Tempo Variance Index (%)
        diffs = np.diff(beats[:, 0]) if beats is not None else np.array([0.5])
        bpms = 60.0 / diffs if len(diffs) > 0 else np.array([120.0])
        avg_bpm = float(np.mean(bpms)) if len(bpms) > 0 else 120.0
        min_bpm = float(np.min(bpms)) if len(bpms) > 0 else 120.0
        max_bpm = float(np.max(bpms)) if len(bpms) > 0 else 120.0
        std_bpm = float(np.std(bpms)) if len(bpms) > 0 else 0.0
        tempo_variance_pct = round((std_bpm / avg_bpm * 100.0) if avg_bpm > 0 else 0.0, 2)
        tempo_style = "Constant BPM (固定極速對拍)" if tempo_variance_pct < 0.8 else "Rubato / Dynamic Tempo (真人彈性律動)"

        downbeat_count = sum(1 for b in beats if int(b[1]) == 1) if beats is not None else 0

        # Audio Fingerprint Checksum Guard (MD5 / SHA256)
        import hashlib
        md5_hash = hashlib.md5()
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
        audio_md5 = md5_hash.hexdigest()

        # Arrangement Dynamic Density Tag
        inst_matrix = blackboard.get_val("instrument_presence", [])
        if inst_matrix:
            avg_active = np.mean([sum(m.values()) for m in inst_matrix if isinstance(m, dict)])
            density_tag = "Sparse Acoustic (純粹原聲/稀疏層次)" if avg_active < 1.5 else ("Dense Full Tutti (全亮爆發/豐富配器)" if avg_active > 2.8 else "Balanced Band (標準樂團編制)")
        else:
            density_tag = "Balanced Band (標準樂團編制)"





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

        json_report_path = os.path.join(output_dir, "pgm_report.json")
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
            "workflow_status": workflow_status,
            "workflow_trace": workflow_trace,
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
                "tempo_curve_plot": plot_path,
                "json_report": json_report_path,
            }
        }
        if contract_validation:
            report["contract_validation"] = contract_validation

        # Write JSON metadata report
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        project_package = self.packager.build(report, output_dir=output_dir)
        report["project_package"] = project_package
        report["outputs"]["project_package_dir"] = project_package["project_package_dir"]
        report["outputs"]["import_guide"] = project_package["import_guide"]

        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        self.packager.build(report, output_dir=output_dir)

        return report
