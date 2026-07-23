"""
Unit tests for CLI batch processor (pgm-craft batch).
"""

import os
import csv
import json
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.cli import run_batch_processing


def test_run_batch_processing():
    with tempfile.TemporaryDirectory() as temp_dir:
        input_dir = os.path.join(temp_dir, "input")
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(input_dir, exist_ok=True)

        sr = 22050
        y = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr))
        sf.write(os.path.join(input_dir, "song1.wav"), y, sr)
        sf.write(os.path.join(input_dir, "song2.wav"), y, sr)

        summary_csv = run_batch_processing(input_dir=input_dir, output_dir=output_dir, max_workers=2)

        assert os.path.exists(summary_csv)
        assert os.path.exists(os.path.join(output_dir, "batch_summary.json"))

        with open(summary_csv, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        assert len(reader) == 2
        filenames = [r["file_name"] for r in reader]
        assert "song1.wav" in filenames
        assert "song2.wav" in filenames
