"""
Unit tests for PodcastSpeechNode speech transcription and alignment node.
"""

import os
import json
import tempfile
import pytest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import PodcastSpeechNode


def test_podcast_speech_node_missing_keys():
    bb = Blackboard()
    node = PodcastSpeechNode()
    missing = bb.validate_strict(node)
    assert "audio_path" in missing


def test_podcast_speech_node_execution():
    bb = Blackboard()
    with tempfile.TemporaryDirectory() as temp_dir:
        sample_audio = os.path.join(temp_dir, "test_speech.wav")
        sr = 22050
        y = np.sin(2 * np.pi * 300 * np.linspace(0, 2.0, sr * 2))
        sf.write(sample_audio, y, sr)

        bb.set_val("audio_path", sample_audio)
        bb.set_val("output_dir", temp_dir)

        node = PodcastSpeechNode()
        status = node.run(bb)

        assert status == NodeStatus.SUCCESS
        assert "subtitles_srt" in bb
        assert "transcript_json" in bb

        srt_path = bb["subtitles_srt"]
        json_path = bb["transcript_json"]
        assert os.path.exists(srt_path)
        assert os.path.exists(json_path)

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()
        assert "-->" in srt_content

        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        assert "transcript" in json_data
