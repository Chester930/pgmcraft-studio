import json
import os

import numpy as np

from pgm_craft.beat_evaluation import (
    evaluate_beats,
    evaluate_downbeats,
    evaluate_report_with_references,
    load_beat_annotations,
    serialize_beats,
    write_evaluation_report,
)
from pgm_craft.cli import attach_beat_evaluation, parse_args


def test_evaluate_beats_mirex_window_counts_matches():
    reference = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]])
    estimated = np.array([[0.02, 1], [0.56, 2], [1.12, 3], [1.5, 4]])

    result = evaluate_beats(reference, estimated, tolerance_seconds=0.07, include_mir_eval=False)

    assert result["reference_count"] == 4
    assert result["estimated_count"] == 4
    assert result["matched_count"] == 3
    assert result["f_measure"] == 0.75
    assert result["p95_abs_error_ms"] is not None


def test_evaluate_downbeats_uses_beat_number_one_only():
    reference = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1]])
    estimated = np.array([[0.01, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.12, 1]])

    result = evaluate_downbeats(reference, estimated, tolerance_seconds=0.07)

    assert result["reference_count"] == 2
    assert result["estimated_count"] == 2
    assert result["matched_count"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


def test_load_beat_annotations_text_and_json(tmp_path):
    txt_path = tmp_path / "beats.tsv"
    txt_path.write_text("time\tbeat\n0.0\t1\n0.5\t2\n1.0\t3\n1.5\t4\n", encoding="utf-8")

    loaded = load_beat_annotations(str(txt_path))
    assert loaded.shape == (4, 2)
    assert loaded[0, 0] == 0.0
    assert loaded[0, 1] == 1.0

    json_path = tmp_path / "report.json"
    json_path.write_text(json.dumps({"refined_beats": serialize_beats(loaded)}), encoding="utf-8")
    loaded_json = load_beat_annotations(str(json_path))
    assert loaded_json.shape == (4, 2)


def test_report_evaluation_and_writer(tmp_path):
    reference_path = tmp_path / "reference.txt"
    reference_path.write_text("0.0 1\n0.5 2\n1.0 3\n1.5 4\n", encoding="utf-8")
    report = {"refined_beats": [[0.01, 1], [0.49, 2], [1.0, 3], [1.5, 4]]}

    evaluation = evaluate_report_with_references(report, reference_beats_path=str(reference_path))
    output_path = write_evaluation_report(evaluation, str(tmp_path))

    assert os.path.exists(output_path)
    assert evaluation["beats"]["f_measure"] == 1.0


def test_cli_reference_args_parse():
    args = parse_args([
        "--audio",
        "sample_test.wav",
        "--reference-beats",
        "beats.txt",
        "--reference-downbeats",
        "downbeats.txt",
        "--beat-eval-tolerance",
        "0.05",
    ])

    assert args.reference_beats == "beats.txt"
    assert args.reference_downbeats == "downbeats.txt"
    assert args.beat_eval_tolerance == 0.05


def test_attach_beat_evaluation_syncs_report_json(tmp_path):
    reference_path = tmp_path / "beats.txt"
    reference_path.write_text("0.0 1\n0.5 2\n1.0 3\n1.5 4\n", encoding="utf-8")
    report_json = tmp_path / "pgm_report.json"
    report = {
        "refined_beats": [[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]],
        "outputs": {"json_report": str(report_json)},
    }
    report_json.write_text(json.dumps(report), encoding="utf-8")

    eval_path = attach_beat_evaluation(report, str(tmp_path), reference_beats_path=str(reference_path))

    assert os.path.exists(eval_path)
    saved = json.loads(report_json.read_text(encoding="utf-8"))
    assert saved["beat_evaluation"]["beats"]["f_measure"] == 1.0
    assert saved["outputs"]["beat_evaluation_json"] == eval_path
