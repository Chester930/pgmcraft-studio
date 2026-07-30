"""SDD Pass 116 - click output gain contract."""

import numpy as np
import soundfile as sf

from pgm_craft.synthesizer import PGMSynthesizer


def test_click_default_gain_is_plus_ten_db():
    assert PGMSynthesizer.CLICK_GAIN_DB == 10.0


def test_click_gain_is_applied_before_click_export(tmp_path):
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(22050, dtype=np.float32), 22050)
    beats = [(0.1, 1)]
    synth = PGMSynthesizer()

    boosted_path, _ = synth.synthesize_click(source, beats, output_dir=tmp_path / "boosted")
    reference_path, _ = synth.synthesize_click(
        source,
        beats,
        output_dir=tmp_path / "reference",
        click_gain_db=0.0,
    )
    boosted, _ = sf.read(boosted_path)
    reference, _ = sf.read(reference_path)
    nonzero = np.abs(reference) > 1e-6
    assert np.isclose(
        np.sqrt(np.mean(boosted[nonzero] ** 2)) / np.sqrt(np.mean(reference[nonzero] ** 2)),
        10.0 ** (10.0 / 20.0),
        rtol=1e-4,
    )
