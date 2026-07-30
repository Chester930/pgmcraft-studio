from pathlib import Path

import app


class _FailingPackager:
    def build(self, report, output_dir="outputs"):
        raise AssertionError("stage3 should not build a DAW package")


class _RecordingPackager:
    def __init__(self):
        self.called = False

    def build(self, report, output_dir="outputs"):
        self.called = True
        package_dir = Path(output_dir) / "pgm_project_package"
        package_dir.mkdir(parents=True, exist_ok=True)
        return {
            "project_package_dir": str(package_dir),
            "zip_archive": str(Path(output_dir) / "pgm_project_package.zip"),
            "import_guide": str(package_dir / "IMPORT_GUIDE.md"),
            "files": {},
        }


class _FakeEngine:
    def __init__(self, report, packager):
        self.report = report
        self.packager = packager
        self.enable_stem_separation = False

    def run(self, *args, **kwargs):
        return self.report


def _minimal_report(tmp_path, outputs=None):
    output_dir = Path(tmp_path)
    tempo_curve = output_dir / "tempo_curve.png"
    json_report = output_dir / "pgm_report.json"
    tempo_curve.write_bytes(b"png")
    return {
        "audio_file": "sample_test.wav",
        "estimated_key": "C Major",
        "average_bpm": 120.0,
        "min_bpm": 120.0,
        "max_bpm": 120.0,
        "total_measures": 4,
        "total_beats": 16,
        "workflow_status": "SUCCESS",
        "quality_report": {},
        "quality_grade": "A",
        "stems": {},
        "beat_validation": {"status": "PASS", "warnings": []},
        "downbeat_refinement": {"status": "PASS", "warnings": []},
        "measure_map_warnings": [],
        "chord_progression": [],
        "outputs": {
            "tempo_curve_plot": str(tempo_curve),
            "json_report": str(json_report),
            **(outputs or {}),
        },
    }


def test_process_pgm_empty_input_returns_full_gradio_tuple():
    result = app.process_pgm("", None, False, "", "stage3")

    assert len(result) == app.PGM_OUTPUT_COUNT
    assert "請輸入影片/音訊 URL" in result[0]


def test_process_pgm_offline_url_guard_returns_full_gradio_tuple(monkeypatch):
    import socket

    def _raise_offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(socket, "create_connection", _raise_offline)

    result = app.process_pgm("https://example.invalid/audio.wav", None, False, "", "stage3")

    assert len(result) == app.PGM_OUTPUT_COUNT
    assert "離線狀態" in result[0]
    assert result[13] == result[0]


def test_process_pgm_stage3_tolerates_missing_export_artifacts(monkeypatch, tmp_path):
    report = _minimal_report(tmp_path, {
        "mix_with_click": None,
        "click_track": None,
        "tempo_map_midi": None,
        "click_guide_midi": None,
    })
    monkeypatch.setattr(app, "engine", _FakeEngine(report, _FailingPackager()))

    result = app.process_pgm("", "sample_test.wav", False, str(tmp_path), "stage3")

    assert len(result) == app.PGM_OUTPUT_COUNT
    assert "總拍數" in result[0]
    assert result[2] is None
    assert result[5] is None
    assert result[10] is None
    assert report["project_package_status"] == "SKIPPED_STAGE3_NO_EXPORT_ARTIFACTS"


def test_process_pgm_full_still_builds_package(monkeypatch, tmp_path):
    packager = _RecordingPackager()
    report = _minimal_report(tmp_path, {
        "mix_with_click": None,
        "click_track": None,
        "tempo_map_midi": None,
        "click_guide_midi": None,
    })
    monkeypatch.setattr(app, "engine", _FakeEngine(report, packager))

    result = app.process_pgm("", "sample_test.wav", False, str(tmp_path), "full")

    assert len(result) == app.PGM_OUTPUT_COUNT
    assert packager.called is True
    assert report["project_package"]["project_package_dir"]
