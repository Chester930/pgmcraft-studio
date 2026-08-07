from unittest.mock import patch

from pgm_craft.cli import main


class DummyEngine:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, audio_path, output_dir="outputs", **kwargs):
        print("engine noise")
        return {
            "audio_file": audio_path,
            "estimated_key": "C Major",
            "average_bpm": 120.0,
            "min_bpm": 120.0,
            "max_bpm": 120.0,
            "total_measures": 1,
            "total_beats": 4,
            "project_package": {"project_package_dir": output_dir},
        }


def test_main_quiet_suppresses_stdout(capsys):
    with patch("pgm_craft.cli.PGMCraftEngine", DummyEngine):
        main(["--audio", "dummy.wav", "--quiet"])

    captured = capsys.readouterr()
    assert captured.out == ""
