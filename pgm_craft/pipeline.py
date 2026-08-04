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

from pgm_craft.beat_evaluation import coerce_beat_array, serialize_beats
from pgm_craft.determinism import enable_deterministic_mode
from pgm_craft.workflow.builder import BTWorkflowEngine
from pgm_craft.packager import PGMProjectPackager


def _float_or_none(value):
    if value is None:
        return None
    return float(value)


def _float_list(values, ndigits=3):
    if values is None:
        return []
    return [round(float(v), ndigits) for v in values]


class PGMCraftEngine:
    def __init__(self, enable_stem_separation=True, validate_contracts=False, deterministic=True):
        # Must run before any BT node executes -- BeatNet/torch/Demucs are all
        # imported lazily inside node execute() methods, so this is early
        # enough to still be before any CUDA context exists.
        if deterministic:
            self.determinism_report = enable_deterministic_mode()
        else:
            self.determinism_report = {"status": "DISABLED"}
        self.enable_stem_separation = enable_stem_separation
        self.validate_contracts = validate_contracts
        self.bt_engine = BTWorkflowEngine()
        self.packager = PGMProjectPackager()

    def run(
        self,
        audio_path,
        output_dir="outputs",
        enable_stem=None,
        target_stage: str = "full",
        module3_candidate_sources=None,
        manual_bar_starts=None,
        user_meter_selection=None,
        allow_temporary_bar_delta=None,
        barstart_v2_postprocess_flags=None,
    ):
        os.makedirs(output_dir, exist_ok=True)
        if enable_stem is not None:
            self.enable_stem_separation = enable_stem
        
        print(f"[BT Broadcaster] 啟動 Behavior Tree 即時廣播與節點執行追蹤: {os.path.basename(audio_path)} (Target: {target_stage})")

        # Run Behavior Tree Workflow Engine
        blackboard = self.bt_engine.run(
            audio_path=audio_path,
            output_dir=output_dir,
            enable_stem=self.enable_stem_separation,
            validate_contracts=self.validate_contracts,
            target_stage=target_stage,
            module3_candidate_sources=module3_candidate_sources,
            manual_bar_starts=manual_bar_starts,
            user_meter_selection=user_meter_selection,
            allow_temporary_bar_delta=allow_temporary_bar_delta,
            barstart_v2_postprocess_flags=barstart_v2_postprocess_flags,
        )

        original_beats_raw = blackboard.get_val("beats")
        beats_raw = blackboard.get_val("refined_beats", original_beats_raw)
        original_beats = coerce_beat_array(original_beats_raw) if original_beats_raw is not None else None
        beats = coerce_beat_array(beats_raw) if beats_raw is not None else None
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
        is_module3 = target_stage in ("module3", "module3_barstart_v2")
        export_ready_stages = {"stage5", "stage6", "full"}
        project_dir = blackboard.get_val("project_dir") or output_dir

        quality_report = blackboard.get_val("quality_report", {})
        quality_grade = blackboard.get_val("quality_grade", "A")

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





        # Generate Tempo Curve Plot -- averaged per bar (小節), not per raw
        # beat-to-beat gap. Beats within a bar are evenly subdivided by
        # design (Pass 128), so plotting every single instantaneous
        # 60/diff reading exposes tiny bar-to-bar duration differences
        # (estimation noise, not real tempo changes) as a jagged,
        # oscillating curve even when every bar's own beats are locally
        # flat. One averaged point per bar reads the way the underlying
        # grid was actually built (Pass 144).
        bar_start_indices = (
            [i for i in range(len(beats)) if int(beats[i, 1]) == 1]
            if beats is not None else []
        )
        plot_times, plot_bpms = [], []
        if len(bar_start_indices) > 1:
            for idx in range(len(bar_start_indices) - 1):
                start_i, end_i = bar_start_indices[idx], bar_start_indices[idx + 1]
                bar_duration = float(beats[end_i, 0] - beats[start_i, 0])
                n_beats_in_bar = end_i - start_i
                if bar_duration > 0 and n_beats_in_bar > 0:
                    plot_times.append(float(beats[start_i, 0]))
                    plot_bpms.append(60.0 * n_beats_in_bar / bar_duration)
        elif beats is not None and len(beats) > 1:
            # No beat-number labels to group by bar (or only one bar) --
            # fall back to the raw per-beat curve rather than show nothing.
            plot_times, plot_bpms = list(beats[:-1, 0]), list(bpms)

        fig, ax = plt.subplots(figsize=(10, 4))
        if plot_times:
            ax.plot(plot_times, plot_bpms, color='#4F46E5', linewidth=1.8, marker='o', markersize=3, label='Per-Bar Avg BPM')
        ax.axhline(avg_bpm, color='#EF4444', linestyle='--', label=f'Avg BPM ({avg_bpm:.1f})')
        ax.set_title("PGMCraft BT Workflow Dynamic Tempo Profile")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("BPM")
        ax.grid(True, alpha=0.3)
        ax.legend()

        report_dir = os.path.join(project_dir, "reports") if is_module3 else output_dir
        os.makedirs(report_dir, exist_ok=True)
        plot_path = os.path.join(report_dir, "tempo_curve.png")
        plt.tight_layout()
        plt.savefig(plot_path, dpi=150)
        plt.close()

        json_report_name = "module3_pipeline_report.json" if is_module3 else "pgm_report.json"
        json_report_path = os.path.join(report_dir, json_report_name)
        report = {
            "audio_file": audio_path,
            "target_stage": target_stage,
            "project_dir": project_dir,
            "estimated_key": estimated_key,
            "average_bpm": round(avg_bpm, 1),
            "min_bpm": round(min_bpm, 1),
            "max_bpm": round(max_bpm, 1),
            "total_beats": len(beats) if beats is not None else 0,
            "total_measures": len(measure_map) if measure_map else (downbeat_count if downbeat_count > 0 else (len(beats) // 4 if beats is not None else 0)),
            "beats": serialize_beats(original_beats) if original_beats is not None else [],
            "refined_beats": serialize_beats(beats) if beats is not None else [],
            "beat_precision_diagnostics": {
                "beats_source": "refined_beats" if blackboard.get_val("refined_beats") is not None else "beats",
                "phase_realignment_report": blackboard.get_val("phase_realignment_report", {}),
                "snap_offsets_ms": _float_list(blackboard.get_val("snap_offsets_ms", [])),
                "downbeat_fix_report": blackboard.get_val("downbeat_fix_report", {}),
                "smoothing_report": blackboard.get_val("smoothing_report", {}),
                "beat_grid_repair_report": blackboard.get_val("beat_grid_repair_report", {}),
                "tempo_oscillation_report": blackboard.get_val("tempo_oscillation_report", {}),
                "downbeat_phase_report": blackboard.get_val("downbeat_phase_report", {}),
                "kick_anchor_snap_report": blackboard.get_val("kick_anchor_snap_report", {}),
                "beat_alignment_score": _float_or_none(blackboard.get_val("beat_alignment_score")),
                "fallback_beat_recalculated": blackboard.get_val("fallback_beat_recalculated", False),
                "fallback_beat_rejected": blackboard.get_val("fallback_beat_rejected", False),
                "fallback_candidate_report": blackboard.get_val("fallback_candidate_report", {}),
            },
            "commercial_beat_quality": blackboard.get_val("commercial_beat_quality", {}),
            "beat_validation": beat_validation,
            "downbeat_refinement": downbeat_refinement,
            "quality_report": quality_report,
            "quality_grade": quality_grade,
            "workflow_status": workflow_status,
            "workflow_trace": workflow_trace,
            "ai_model_status": blackboard.get_val("ai_model_status", {}),
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
                "chord_guide_midi": blackboard.get_val("chord_guide_midi"),
                "melody_lead_midi": blackboard.get_val("melody_lead_midi"),
                "vocal_pitch_midi": blackboard.get_val("vocal_pitch_midi"),
                "vocal_lead_quantized_midi": blackboard.get_val("vocal_lead_quantized_midi"),
                "pitch_contour_json": blackboard.get_val("pitch_contour_json"),
                "subtitles_srt": blackboard.get_val("subtitles_srt"),
                "transcript_json": blackboard.get_val("transcript_json"),
                "instrument_presence_json": blackboard.get_val("instrument_presence_json"),
                "sections_json": blackboard.get_val("sections_json"),
                "measure_map_json": blackboard.get_val("measure_map_json"),
                "module3_report_json": blackboard.get_val("module3_report_json"),
                "rhythm_submix": blackboard.get_val("rhythm_submix"),
                "harmonic_submix": blackboard.get_val("harmonic_submix"),
                "structure_submix": blackboard.get_val("structure_submix"),
                "backing_with_click": blackboard.get_val("backing_with_click_path"),
                "tempo_curve_plot": plot_path,
                "json_report": json_report_path,
            },
            "module3_outputs": blackboard.get_val("module3_outputs", {}),
            "segment_source_map": blackboard.get_val("segment_source_map", []),
            "beat_synthesis_report": blackboard.get_val("beat_synthesis_report", {}),
            "subdivision_grid": blackboard.get_val("subdivision_grid", []),
            "syncopation_events": blackboard.get_val("syncopation_events", []),
            "barstart_v2_report": blackboard.get_val("barstart_v2_report", {}),
            "barstart_v2_auto_report": blackboard.get_val("barstart_v2_auto_report", {}),
            "bar_length_report": blackboard.get_val("bar_length_report", {}),
            "committed_bar_starts": blackboard.get_val("committed_bar_starts", []),
            "active_bar_probe_window": blackboard.get_val("active_bar_probe_window", {}),
            "bar_probe_windows": blackboard.get_val("bar_probe_windows", []),
            "bar_probe_policy": blackboard.get_val("bar_probe_policy", {}),
            "drum_bar_evidence_report": blackboard.get_val("drum_bar_evidence_report", {}),
            "bar_start_decision_report": blackboard.get_val("bar_start_decision_report", {}),
            "unresolved_bar_spans": blackboard.get_val("unresolved_bar_spans", []),
        }
        if contract_validation:
            report["contract_validation"] = contract_validation

        if is_module3:
            module3_outputs = dict(report.get("module3_outputs", {}) or {})
            module3_outputs.update({
                "tempo_curve_plot": plot_path,
                "pipeline_report_json": json_report_path,
                "json_report": json_report_path,
                "project_package_status": "SKIPPED_MODULE3_TEST_PROJECT",
            })
            report["module3_outputs"] = module3_outputs

        # 1. Write placeholder JSON first so packager can locate the file for copying
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        if is_module3:
            report["project_package_status"] = "SKIPPED_MODULE3_TEST_PROJECT"
            with open(json_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            return report

        if target_stage not in export_ready_stages:
            report["project_package_status"] = f"SKIPPED_{str(target_stage).upper()}_NO_EXPORT_ARTIFACTS"
            report["outputs"]["project_package_dir"] = None
            report["outputs"]["import_guide"] = None
            with open(json_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            return report

        # 2. Build DAW project package (copies JSON into reports/ dir)
        project_package = self.packager.build(report, output_dir=output_dir)
        report["project_package"] = project_package
        report["outputs"]["project_package_dir"] = project_package["project_package_dir"]
        report["outputs"]["import_guide"] = project_package["import_guide"]

        # 3. Overwrite JSON with final complete report (includes project_package)
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 4. Sync final JSON into the package reports dir copy
        packaged_json = project_package.get("files", {}).get("json_report")
        if packaged_json and os.path.isfile(packaged_json):
            import shutil as _shutil
            _shutil.copy2(json_report_path, packaged_json)

        return report
