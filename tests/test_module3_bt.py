import os

import numpy as np
import soundfile as sf

from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.workflow.audio_nodes import MeasureMapNode, SectionStructureNode
from pgm_craft.workflow.audio_quality_bt import DeReverbFilterNode, SeparateCrowdNode
from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_bt import (
    BeatGridSynthesisNode,
    CandidateTrackBuildNode,
    Module3BarStartV2MergeNode,
    Module3OutputSummaryNode,
    PerTrackBeatAnalysisNode,
    PerSegmentConfidenceNode,
    SegmentSourceAttributionNode,
    SubdivisionGridNode,
    SyncopationClassificationNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class _MockSeparator:
    def separate_crowd(self, audio_path, output_dir):
        import os

        os.makedirs(output_dir, exist_ok=True)
        crowd_path = os.path.join(output_dir, "crowd_cheering.wav")
        no_crowd_path = os.path.join(output_dir, "no_crowd.wav")
        open(crowd_path, "wb").close()
        open(no_crowd_path, "wb").close()
        return crowd_path, no_crowd_path

    def process_dereverb(self, audio_path, output_dir):
        import os

        os.makedirs(output_dir, exist_ok=True)
        dry_path = os.path.join(output_dir, "dereverb_dry.wav")
        room_path = os.path.join(output_dir, "reverb_room.wav")
        open(dry_path, "wb").close()
        open(room_path, "wb").close()
        return dry_path, room_path


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_module3_tree_is_narrow_click_workflow():
    tree = build_master_pipeline_tree(target_stage="module3")
    names = _node_names(tree)

    assert tree.name == "Module3BeatClickRoot"
    assert "CandidateTrackBuildNode" in names
    assert "SynthesizeRhythmTrackNode" in names
    assert "PrepareInstrumentalTrackNode" in names
    assert "TrackA_RhythmBranch" in names
    assert "TrackB_InstrumentalBranch" in names
    assert "MultiModelBeatEnsembleNode" in names
    assert "BeatFusionArbitratorNode" in names
    assert "SegmentSourceAttributionNode" in names
    assert "BeatGridSynthesisNode" in names
    assert "OnsetPhaseRealignmentNode" in names
    assert "MicroTimingTransientSnapNode" in names
    assert "ViterbiTempoSmoothingNode" in names
    assert "SubdivisionGridNode" in names
    assert "Module3BarStartV2MergeNode" in names
    assert "Module3ExportRoot" in names
    assert "Module3BackingWithClickNode" in names

    assert "MIDIExportNode" not in names
    assert "PodcastSpeechNode" not in names
    assert "VoiceSplitMIDIExportNode" not in names
    assert "PackageRoot" not in names


def test_module3_barstart_v2_merge_node_compares_but_does_not_promote_when_v2_incomplete(tmp_path):
    """Pass 142: v2 no longer needs human reference/manual acceptance nor to
    outscore v1 -- it is adopted whenever it completes cleanly. But when the
    real v2 engine (given a silent audio fixture and no manual bar-start
    seed) genuinely cannot resolve the whole song, it must leave
    unresolved_bar_spans and v1's own beats must survive untouched rather
    than shipping a grid with known gaps."""
    audio_path = tmp_path / "source.wav"
    sf.write(audio_path, np.zeros(22050 * 4, dtype=np.float32), 22050)

    bb = Blackboard()
    beats = np.array([
        [0.0, 1],
        [0.5, 2],
        [1.0, 3],
        [1.5, 4],
        [2.0, 1],
        [2.5, 2],
        [3.0, 3],
        [3.5, 4],
    ], dtype=float)
    bb.set_val("beats", beats.copy())
    bb.set_val("refined_beats", beats.copy())
    bb.set_val("audio_duration_sec", 4.0)  # keeps the real v2 walk bounded/fast
    bb.set_val("click_track", "main_click.wav")
    bb.set_val("audio_path", str(audio_path))
    bb.set_val("project_dir", str(tmp_path))

    assert Module3BarStartV2MergeNode().execute(bb) == NodeStatus.SUCCESS

    # v1's own grid must be completely untouched: no reference/manual
    # acceptance was ever recorded, so promotion_gate can never be satisfied.
    np.testing.assert_array_equal(bb.get_val("beats"), beats)
    np.testing.assert_array_equal(bb.get_val("refined_beats"), beats)
    np.testing.assert_array_equal(bb.get_val("module3_legacy_beats"), beats)
    assert bb.get_val("click_track") == "main_click.wav"
    assert bb.get_val("barstart_v2_promoted_to_main") is False

    v2_grid = bb.get_val("barstart_v2_grid_beats")
    assert v2_grid is not None and len(v2_grid) > 0

    assert bb.get_val("barstart_v2_click_track").endswith("barstart_v2_click_track.wav")
    assert bb.get_val("barstart_v2_mix_with_click").endswith("barstart_v2_mix_with_click.wav")
    assert bb.get_val("module3_legacy_click_track").endswith("legacy_click_track.wav")
    assert bb.get_val("module3_legacy_mix_with_click").endswith("legacy_mix_with_click.wav")
    assert os.path.exists(bb.get_val("barstart_v2_click_track"))
    assert os.path.exists(bb.get_val("barstart_v2_mix_with_click"))
    assert os.path.exists(bb.get_val("module3_legacy_click_track"))
    assert os.path.exists(bb.get_val("module3_legacy_mix_with_click"))

    report = bb.get_val("barstart_v2_report")
    assert report["status"] == "COMPARED_NOT_PROMOTED"
    assert report["replaces_module3_click"] is False
    assert report["promotion_gate"]["status"] == "V2_INCOMPLETE"
    assert "UNRESOLVED_BAR_SPANS_PRESENT" in report["promotion_gate"]["blockers"]
    assert report["unresolved_bar_span_count"] > 0
    assert report["comparison_artifacts"]["status"] == "EXPORTED"
    assert report["legacy_artifacts"]["status"] == "EXPORTED"
    assert "original_score" in report["quality_comparison"]
    assert "barstart_v2_score" in report["quality_comparison"]
    assert "manual_listening_evaluation" not in report


def test_module3_barstart_v2_merge_node_promotes_when_v2_completes_cleanly(tmp_path):
    """Pass 142: v2 replaces v1's grid whenever it completes with zero
    unresolved bar spans -- no reference/manual acceptance fields needed at
    all (real listening tests already confirmed v2 sounds better than v1,
    so there is nothing left to gate on beyond "did v2 actually finish")."""
    audio_path = tmp_path / "source.wav"
    sf.write(audio_path, np.zeros(22050 * 4, dtype=np.float32), 22050)

    bb = Blackboard()
    # deliberately irregular v1 grid: wildly inconsistent inter-beat spacing
    bad_beats = np.array([
        [0.0, 1],
        [0.05, 2],
        [3.0, 3],
        [3.02, 4],
        [3.5, 1],
        [8.0, 2],
        [8.01, 3],
        [8.5, 4],
    ], dtype=float)
    bb.set_val("beats", bad_beats.copy())
    bb.set_val("refined_beats", bad_beats.copy())
    bb.set_val("audio_path", str(audio_path))
    bb.set_val("project_dir", str(tmp_path))
    bb.set_val("audio_duration_sec", 4.0)
    # pre-seeding the whole song as manual_bar_starts means the walking loop
    # stops before spending a single probe tick, so zero unresolved spans
    # accumulate -- this is what a real reference-verified grid looks like.
    bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0, 3.0, 4.0])
    # No barstart_v2_reference_acceptance / barstart_v2_manual_acceptance
    # set -- Pass 142 retired that requirement entirely.

    assert Module3BarStartV2MergeNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("barstart_v2_report")
    assert report["promotion_gate"]["status"] == "V2_READY"
    assert report["unresolved_bar_span_count"] == 0
    assert report["quality_comparison"]["v2_scores_higher"] is True
    assert report["status"] == "PROMOTED_TO_MODULE3_DEFAULT"
    assert report["replaces_module3_click"] is True

    assert bb.get_val("barstart_v2_promoted_to_main") is True
    np.testing.assert_array_equal(bb.get_val("beats"), bb.get_val("barstart_v2_grid_beats"))
    np.testing.assert_array_equal(bb.get_val("refined_beats"), bb.get_val("barstart_v2_grid_beats"))
    np.testing.assert_array_equal(bb.get_val("module3_legacy_beats"), bad_beats)


def test_module3_uses_shared_stage3_nodes_in_module3_composition():
    module3_tree = build_master_pipeline_tree(target_stage="module3")
    full_stage3_tree = build_master_pipeline_tree(target_stage="stage3")
    module3_names = _node_names(module3_tree)
    stage3_names = _node_names(full_stage3_tree)

    shared_nodes = [
        "SynthesizeRhythmTrackNode",
        "PrepareInstrumentalTrackNode",
        "KickSnarePulseNode",
        "TrackA_RhythmBranch",
        "TrackB_InstrumentalBranch",
        "MultiModelBeatEnsembleNode",
        "BeatFusionArbitratorNode",
        "ReEntryReAnchoringNode",
        "BeatValidationNode",
        "DownbeatRefineNode",
        "DrumFillDetectionNode",
        "OnsetPhaseRealignmentNode",
        "MicroTimingTransientSnapNode",
        "KickBassDownbeatVerifierNode",
        "ViterbiTempoSmoothingNode",
        "BeatAlignmentVerificationAndFallback",
    ]

    for name in shared_nodes:
        assert name in stage3_names
        assert name in module3_names

    assert module3_names.index("BeatGridSynthesisNode") < module3_names.index("OnsetPhaseRealignmentNode")


def test_candidate_tracks_keep_full_mix_unseparated(tmp_path):
    denoised = tmp_path / "denoised_full_mix.wav"
    normalized = tmp_path / "normalized_full_mix.wav"
    drum_target = tmp_path / "drums.wav"
    denoised.write_bytes(b"")
    normalized.write_bytes(b"")
    drum_target.write_bytes(b"")

    bb = Blackboard()
    bb.set_val("audio_path", str(normalized))
    bb.set_val("denoised_wav_path", str(denoised))
    bb.set_val("target_analysis_path", str(drum_target))
    bb.set_val("project_dir", str(tmp_path))

    assert CandidateTrackBuildNode().execute(bb) == NodeStatus.SUCCESS

    tracks = bb.get_val("beat_candidate_tracks")
    assert tracks["full_mix"]["path"] == str(denoised)


def test_candidate_track_selection_controls_enabled_sources(tmp_path):
    denoised = tmp_path / "denoised_full_mix.wav"
    denoised.write_bytes(b"fixture")

    bb = Blackboard()
    bb.set_val("audio_path", str(denoised))
    bb.set_val("denoised_wav_path", str(denoised))
    bb.set_val("project_dir", str(tmp_path))
    bb.set_val("module3_candidate_sources", ["rhythm"])

    assert CandidateTrackBuildNode().execute(bb) == NodeStatus.SUCCESS

    tracks = bb.get_val("beat_candidate_tracks")
    assert tracks["full_mix"]["selected"] is False
    assert tracks["full_mix"]["enabled"] is False
    assert tracks["rhythm"]["selected"] is True
    assert tracks["rhythm"]["enabled"] is False


def test_per_track_analysis_skips_unselected_candidate_sources():
    bb = Blackboard()
    beats_full = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]])
    beats_rhythm = np.array([[2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4]])
    bb.set_val("beats_full_mix", beats_full)
    bb.set_val("beats_rhythm", beats_rhythm)
    bb.set_val("beat_candidate_tracks", {
        "full_mix": {"enabled": False, "path": "full.wav", "base_weight": 0.78},
        "rhythm": {"enabled": True, "path": "rhythm.wav", "base_weight": 1.0},
    })

    assert PerTrackBeatAnalysisNode().execute(bb) == NodeStatus.SUCCESS

    candidates = bb.get_val("beat_candidates")
    assert "full_mix" not in candidates
    assert "rhythm" in candidates
    np.testing.assert_array_equal(candidates["rhythm"]["beats"], beats_rhythm)


def test_module3_pipeline_skips_pgm_packaging(tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fixture")

    bb = Blackboard()
    bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]))
    bb.set_val("refined_beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]))
    bb.set_val("workflow_status", "SUCCESS")
    bb.set_val("click_track", str(tmp_path / "click_track.wav"))
    bb.set_val("mix_with_click", str(tmp_path / "mix_with_click.wav"))
    bb.set_val("module3_report_json", str(tmp_path / "module3_beat_click_report.json"))
    bb.set_val("module3_outputs", {"click_track": bb.get_val("click_track")})
    bb.set_val("segment_source_map", [{"measure": 1, "primary_source": "full_mix"}])
    bb.set_val("project_dir", str(tmp_path / "module3_project"))

    engine = PGMCraftEngine(enable_stem_separation=False)
    engine.bt_engine.run = lambda *args, **kwargs: bb

    def _fail_packager(*args, **kwargs):
        raise AssertionError("module3 must not build full PGM package")

    engine.packager.build = _fail_packager

    report = engine.run(str(audio_path), output_dir=str(tmp_path), target_stage="module3")

    assert report["project_package_status"] == "SKIPPED_MODULE3_TEST_PROJECT"
    assert "project_package" not in report
    assert report["outputs"]["json_report"].endswith("module3_pipeline_report.json")
    assert report["module3_outputs"]["pipeline_report_json"] == report["outputs"]["json_report"]
    assert report["module3_outputs"]["project_package_status"] == "SKIPPED_MODULE3_TEST_PROJECT"


def test_module3_output_summary_writes_manifest(tmp_path):
    bb = Blackboard()
    bb.set_val("project_dir", str(tmp_path))
    bb.set_val("audio_path", str(tmp_path / "source" / "song.wav"))
    bb.set_val("raw_wav_path", str(tmp_path / "source" / "song_raw.wav"))
    bb.set_val("normalized_wav_path", str(tmp_path / "source" / "song_normalized.wav"))
    bb.set_val("denoised_wav_path", str(tmp_path / "source" / "song_denoised.wav"))
    bb.set_val("click_track", str(tmp_path / "click" / "click_track.wav"))
    bb.set_val("mix_with_click", str(tmp_path / "click" / "mix_with_click.wav"))
    bb.set_val("backing_with_click_status", "SKIPPED_NO_NO_VOCAL_SOURCE")
    bb.set_val("beat_candidate_tracks", {
        "full_mix": {"path": "full.wav", "role": "original reference", "enabled": True, "base_weight": 0.78}
    })
    bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]))

    assert Module3OutputSummaryNode().execute(bb) == NodeStatus.SUCCESS

    outputs = bb.get_val("module3_outputs")
    assert outputs["test_project_dir"] == str(tmp_path)
    assert outputs["reports_dir"] == str(tmp_path / "reports")
    assert outputs["source_audio"].endswith("song.wav")
    assert outputs["candidate_tracks"]["full_mix"]["enabled"] is True
    assert outputs["candidate_tracks"]["full_mix"]["selected"] is False
    assert outputs["candidate_tracks"]["full_mix"]["available"] is False
    assert outputs["backing_with_click_status"] == "SKIPPED_NO_NO_VOCAL_SOURCE"
    assert outputs["module3_report_json"].endswith("module3_beat_click_report.json")


def test_project_scoped_intermediate_outputs(tmp_path):
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"fixture")
    project_dir = tmp_path / "Song"
    (project_dir / "source").mkdir(parents=True)
    (project_dir / "reports").mkdir()

    bb = Blackboard()
    bb.set_val("audio_path", str(audio_path))
    bb.set_val("output_dir", str(tmp_path))
    bb.set_val("project_dir", str(project_dir))
    bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]))
    bb.set_val("refined_beats", bb.get_val("beats"))
    bb.set_val("beat_validation", {"status": "PASS"})
    bb.set_val("downbeat_refinement", {"source": "downbeat"})

    assert SeparateCrowdNode(_MockSeparator()).execute(bb) == NodeStatus.SUCCESS
    assert DeReverbFilterNode(_MockSeparator()).execute(bb) == NodeStatus.SUCCESS
    assert MeasureMapNode().execute(bb) == NodeStatus.SUCCESS
    assert SectionStructureNode().execute(bb) == NodeStatus.SUCCESS

    assert str(project_dir / "source") in bb.get_val("crowd_path")
    assert str(project_dir / "source") in bb.get_val("dereverb_dry_path")
    assert bb.get_val("measure_map_json") == str(project_dir / "reports" / "measure_map.json")
    assert bb.get_val("sections_json") == str(project_dir / "reports" / "sections.json")


def test_segment_source_attribution_synthesizes_by_measure():
    bb = Blackboard()
    bb.set_val("analysis_segments", [
        {"segment_index": 0, "measure": 1, "start_time": 0.0, "end_time": 2.0},
        {"segment_index": 1, "measure": 2, "start_time": 2.0, "end_time": 4.0},
    ])
    bb.set_val("beat_candidates", {
        "full_mix": {
            "source": "full_mix",
            "base_weight": 0.78,
            "beats": np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]]),
        },
        "rhythm": {
            "source": "rhythm",
            "base_weight": 1.0,
            "beats": np.array([[2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4]]),
        },
        "vocal": {
            "source": "vocal",
            "base_weight": 0.48,
            "beats": np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1]]),
        },
    })
    bb.set_val("beat_candidate_tracks", {})

    assert PerSegmentConfidenceNode().execute(bb) == NodeStatus.SUCCESS
    assert SegmentSourceAttributionNode().execute(bb) == NodeStatus.SUCCESS
    assert BeatGridSynthesisNode().execute(bb) == NodeStatus.SUCCESS

    source_map = bb.get_val("segment_source_map")
    assert source_map[0]["primary_source"] == "full_mix"
    assert source_map[1]["primary_source"] == "rhythm"

    beats = bb.get_val("refined_beats")
    assert len(beats) == 8
    assert np.all(np.diff(beats[:, 0]) > 0)
    assert bb.get_val("beat_synthesis_report")["segments"][1]["chosen_source"] == "rhythm"


def test_subdivision_grid_classifies_anticipation_without_snapping_click():
    bb = Blackboard()
    bb.set_val("beats", np.array([
        [0.0, 1],
        [0.5, 2],
        [1.0, 3],
        [1.5, 4],
        [2.0, 1],
    ]))
    bb.set_val("onset_events", [{"time": 1.76}])

    assert SubdivisionGridNode().execute(bb) == NodeStatus.SUCCESS
    assert SyncopationClassificationNode().execute(bb) == NodeStatus.SUCCESS

    events = bb.get_val("syncopation_events")
    assert events[0]["nearest_subdivision"] == "4&"
    assert events[0]["nearest_click_beat"] == "1"
    assert events[0]["classification"] == "anticipation"
    assert events[0]["snap_click"] is False
    assert bb.get_val("snap_exclusion_zones")
