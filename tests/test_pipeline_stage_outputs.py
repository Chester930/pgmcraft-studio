import numpy as np

from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.workflow.nodes import Blackboard


class _FailingPackager:
    def build(self, report, output_dir="outputs"):
        raise AssertionError("non-export stages should not build a DAW package")


class _RecordingPackager:
    def __init__(self):
        self.called = False

    def build(self, report, output_dir="outputs"):
        self.called = True
        return {
            "project_package_dir": str(output_dir / "pgm_project_package") if hasattr(output_dir, "__truediv__") else f"{output_dir}/pgm_project_package",
            "zip_archive": None,
            "import_guide": "IMPORT_GUIDE.md",
            "files": {},
        }


def _blackboard():
    bb = Blackboard()
    beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]])
    bb.set_val("beats", beats)
    bb.set_val("refined_beats", beats)
    bb.set_val("workflow_status", "SUCCESS")
    bb.set_val("workflow_trace", [])
    return bb


def test_engine_stage3_skips_project_package(tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fixture")

    engine = PGMCraftEngine(enable_stem_separation=False)
    engine.bt_engine.run = lambda *args, **kwargs: _blackboard()
    engine.packager = _FailingPackager()

    report = engine.run(str(audio_path), output_dir=str(tmp_path), target_stage="stage3")

    assert "project_package" not in report
    assert report["project_package_status"] == "SKIPPED_STAGE3_NO_EXPORT_ARTIFACTS"
    assert report["outputs"]["project_package_dir"] is None
    assert report["outputs"]["import_guide"] is None


def test_engine_full_builds_project_package(tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fixture")
    packager = _RecordingPackager()

    engine = PGMCraftEngine(enable_stem_separation=False)
    engine.bt_engine.run = lambda *args, **kwargs: _blackboard()
    engine.packager = packager

    report = engine.run(str(audio_path), output_dir=str(tmp_path), target_stage="full")

    assert packager.called is True
    assert "project_package" in report
    assert report["outputs"]["project_package_dir"]
