"""
PGMCraft Command Line Interface (CLI)
Allows running PGM Stem Separation & Audio Analysis via Terminal.
"""

import os
import sys
import json
import argparse
import contextlib
from pgm_craft.beat_evaluation import evaluate_report_with_references, write_evaluation_report
from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.workflow.builder import build_pgm_workflow_tree


def export_workflow_schema(output_dir="outputs") -> str:
    """Exports all registered BT nodes, required/optional/output keys as JSON Schema."""
    os.makedirs(output_dir, exist_ok=True)
    tree = build_pgm_workflow_tree()
    nodes_info = []

    def collect_nodes(node):
        if hasattr(node, "children"):
            for child in node.children:
                collect_nodes(child)
        else:
            nodes_info.append({
                "name": node.name,
                "node_type": node.__class__.__name__,
                "required_keys": getattr(node, "required_keys", []),
                "optional_keys": getattr(node, "optional_keys", []),
                "output_keys": getattr(node, "output_keys", []),
            })

    collect_nodes(tree)
    schema_path = os.path.join(output_dir, "pgm_workflow_schema.json")
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump({"workflow": "PGMCraftWorkflowRoot", "nodes": nodes_info}, f, ensure_ascii=False, indent=2)

    return schema_path


def print_cli_diagnostics(report: dict):
    """Prints formatted Behavior Tree Trace & Diagnostics to terminal stdout."""
    trace = report.get("workflow_trace", [])
    validations = report.get("contract_validation", [])
    status = report.get("workflow_status", "UNKNOWN")

    print("\n" + "=" * 65)
    print(" 🔍  PGMCraft Behavior Tree Trace & Diagnostics ")
    print("=" * 65)
    print(f" Workflow Status: {status}")
    print(f" Total Executed Nodes: {len(trace)}")
    print("-" * 65)
    print(f"{'#':<3} | {'Node Name':<22} | {'Status':<8} | {'Duration (ms)':<12}")
    print("-" * 65)

    for entry in trace:
        idx = entry.get("index", 0)
        node = entry.get("node", "N/A")
        n_status = entry.get("status", "N/A")
        dur = entry.get("duration_ms", 0.0)
        print(f"{idx:<3} | {node:<22} | {n_status:<8} | {dur:<12.2f}")

    if validations:
        print("-" * 65)
        print(" 📜 Blackboard Contract Warnings:")
        has_warnings = False
        for val in validations:
            missing = val.get("missing_required_keys", [])
            if missing:
                has_warnings = True
                print(f"  ⚠️ Node [{val.get('node')}] missing keys: {missing}")
        if not has_warnings:
            print("  ✅ All node contract validations PASSED!")

    print("=" * 65 + "\n")


def attach_beat_evaluation(
    report: dict,
    output_dir: str,
    reference_beats_path: str = None,
    reference_downbeats_path: str = None,
    tolerance_seconds: float = 0.07,
) -> str:
    """Runs reference-based beat evaluation and syncs it into report JSON files."""
    evaluation = evaluate_report_with_references(
        report,
        reference_beats_path=reference_beats_path,
        reference_downbeats_path=reference_downbeats_path,
        tolerance_seconds=tolerance_seconds,
    )
    evaluation_path = write_evaluation_report(evaluation, output_dir)
    report["beat_evaluation"] = evaluation
    report.setdefault("outputs", {})["beat_evaluation_json"] = evaluation_path

    json_report = report.get("outputs", {}).get("json_report") or os.path.join(output_dir, "pgm_report.json")
    if json_report:
        with open(json_report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    packaged_json = report.get("project_package", {}).get("files", {}).get("json_report")
    if packaged_json and os.path.isfile(packaged_json):
        import shutil as _shutil
        _shutil.copy2(json_report, packaged_json)

    return evaluation_path


def run_batch_processing(input_dir: str, output_dir: str = "outputs", max_workers: int = 4) -> str:
    """Runs batch PGM pipeline processing on a folder of audio files."""
    import csv
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    os.makedirs(output_dir, exist_ok=True)
    summary_csv = os.path.join(output_dir, "batch_summary.csv")
    summary_json = os.path.join(output_dir, "batch_summary.json")

    valid_exts = (".wav", ".mp3", ".flac", ".m4a")
    audio_files = [
        os.path.join(input_dir, f) for f in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, f)) and f.lower().endswith(valid_exts)
    ]
    audio_files.sort(key=lambda path: os.path.basename(path).lower())

    results = []

    def process_single(file_path):
        fname = os.path.basename(file_path)
        sub_output = os.path.join(output_dir, os.path.splitext(fname)[0])
        try:
            engine = PGMCraftEngine()
            rep = engine.run(file_path, output_dir=sub_output)
            return {
                "file_name": fname,
                "status": "SUCCESS",
                "key": rep.get("estimated_key", "N/A"),
                "bpm": rep.get("average_bpm", 0.0),
                "measures": rep.get("total_measures", 0),
                "package_dir": rep.get("project_package", {}).get("project_package_dir", sub_output)
            }
        except Exception as exc:
            return {
                "file_name": fname,
                "status": f"FAILED: {exc}",
                "key": "N/A",
                "bpm": 0.0,
                "measures": 0,
                "package_dir": sub_output
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single, f) for f in audio_files]
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda row: row["file_name"].lower())

    with open(summary_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file_name", "status", "key", "bpm", "measures", "package_dir"])
        writer.writeheader()
        writer.writerows(results)

    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump({"batch_results": results}, f, ensure_ascii=False, indent=2)

    return summary_csv


def build_parser():
    parser = argparse.ArgumentParser(
        description="PGMCraft Studio: AI Audio Stem Separation, Music Transcription & PGM Backing Track Suite"
    )
    parser.add_argument("--audio", "-a", help="Path to input audio file (.mp3 / .wav / .flac)")
    parser.add_argument("--batch-dir", "-b", help="Path to folder containing multiple audio files for batch processing")
    parser.add_argument("--output", "-o", default="outputs", help="Output directory path (default: ./outputs)")
    parser.add_argument("--stem", "-s", action="store_true", help="Enable Demucs AI stem separation")
    parser.add_argument("--daw-profile", choices=["reaper", "ableton", "logic", "cubase", "all"], default="all", help="Target DAW export profile (default: all)")
    parser.add_argument("--target-stage", choices=["stage1", "stage2", "stage3", "stage4", "stage5", "stage6", "module3", "full"], default="full", help="Behavior Tree target stage (default: full)")
    parser.add_argument("--plugin-dir", help="Path to custom Behavior Tree node plugins directory")
    parser.add_argument("--diagnostics", "-d", action="store_true", help="Print detailed workflow execution trace & contract diagnostics")
    parser.add_argument("--export-schema", action="store_true", help="Export workflow node JSON schema")
    parser.add_argument("--reference-beats", help="Reference beat annotation file for objective beat precision evaluation")
    parser.add_argument("--reference-downbeats", help="Reference downbeat annotation file for objective downbeat precision evaluation")
    parser.add_argument("--beat-eval-tolerance", type=float, default=0.07, help="Beat/downbeat match tolerance in seconds (default: 0.07)")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum workers for --batch-dir processing (default: 4)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress console stdout logging for CI/CD or automated script integration")
    return parser


def parse_args(args_list=None):
    return build_parser().parse_args(args_list)


def _stdout_context(quiet: bool):
    if not quiet:
        return contextlib.nullcontext()
    return open(os.devnull, "w", encoding="utf-8")


def main(args_list=None):
    parser = build_parser()
    args = parser.parse_args(args_list)

    if args.max_workers < 1:
        parser.error("--max-workers must be at least 1")

    with _stdout_context(args.quiet) as quiet_stdout:
        stdout_redirect = contextlib.redirect_stdout(quiet_stdout) if args.quiet else contextlib.nullcontext()
        with stdout_redirect:
            if args.plugin_dir:
                from pgm_craft.plugin_loader import PluginLoader
                loader = PluginLoader(plugin_dirs=[args.plugin_dir])
                loaded = loader.load_plugins()
                print(f"🔌 Loaded {len(loaded)} custom BT node plugins from: {args.plugin_dir}")

            if args.export_schema:
                schema_path = export_workflow_schema(output_dir=args.output)
                print(f"✅ Workflow JSON Schema exported to: {schema_path}")
                if not args.audio and not args.batch_dir:
                    return

            if args.batch_dir:
                summary_path = run_batch_processing(
                    input_dir=args.batch_dir,
                    output_dir=args.output,
                    max_workers=args.max_workers,
                )
                print(f"✅ Batch processing complete! Summary written to: {summary_path}")
                return

            if not args.audio:
                parser.error("the following arguments are required: --audio / -a or --batch-dir / -b (or use --export-schema)")

            engine = PGMCraftEngine(enable_stem_separation=args.stem, validate_contracts=args.diagnostics)
            report = engine.run(args.audio, output_dir=args.output, target_stage=args.target_stage)
            evaluation_path = None
            if args.reference_beats or args.reference_downbeats:
                evaluation_path = attach_beat_evaluation(
                    report,
                    output_dir=args.output,
                    reference_beats_path=args.reference_beats,
                    reference_downbeats_path=args.reference_downbeats,
                    tolerance_seconds=args.beat_eval_tolerance,
                )

            print("\n" + "=" * 50)
            print(" 🎛️  PGMCraft Studio Processing Report ")
            print("=" * 50)
            print(f" 音檔名稱: {report['audio_file']}")
            print(f" 音樂調性 (Key): {report['estimated_key']}")
            print(f" 平均速度 (BPM): {report['average_bpm']} (範圍: {report['min_bpm']} ~ {report['max_bpm']})")
            print(f" 總小節數: {report['total_measures']} 小節 | 總拍數: {report['total_beats']} 拍")
            print(f" 產出目錄: {args.output}")
            print(f" 工程素材包: {report.get('project_package', {}).get('project_package_dir', '未建立')}")
            if evaluation_path:
                print(f" 節拍精度評估: {evaluation_path}")
            print("=" * 50 + "\n")

            if args.diagnostics:
                print_cli_diagnostics(report)


if __name__ == "__main__":
    main()
