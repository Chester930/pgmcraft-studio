# Architecture

**Last Updated:** 2026-07-22

## Architectural Style

PGMCraft Studio uses a node-based audio workflow orchestrated by a Behavior Tree.

The intended architecture is:

```text
Input Source
  -> Workflow Nodes
  -> Blackboard State
  -> Behavior Tree Orchestration
  -> Output Package
```

This makes the project suitable for incremental growth. New capabilities should be added as nodes, then connected through Behavior Tree structure.

## Core Concepts

### Node

A node is one small unit of work.

Examples:

- detect whether input is a URL
- download media
- load audio
- check signal quality
- run beat tracking
- export MIDI
- synthesize click audio
- write reports

Nodes should avoid owning the whole workflow. They should read required values from the blackboard, perform one clear job, write results back, and return a status.

### Blackboard

The blackboard is shared workflow state.

Common keys:

- `audio_path`
- `output_dir`
- `y`
- `sr`
- `target_analysis_path`
- `beats`
- `estimated_key`
- `chord_progression`
- `click_track`
- `mix_with_click`
- `tempo_map_midi`
- `stems`

As the project matures, these keys should be documented or typed to reduce accidental coupling.

### Behavior Tree

The Behavior Tree decides execution order and fallback behavior.

Current core shape:

```text
Root Sequence
├── VideoURLDownloadNode
├── AudioLoadNode
├── DemucsStemNode
├── Fallback: BeatTrackingSelector
│   ├── BeatNetNode
│   └── LibrosaBeatNode
├── KeyChordAnalysisNode
├── ClickSynthesisNode
└── MIDIExportNode
```

This structure means:

- required preparation steps run in order
- optional stem separation can be skipped
- BeatNet is preferred
- Librosa is the fallback
- export nodes run only after analysis succeeds

## Node Categories

### Input Nodes

Purpose:

- receive local file or URL
- download media if needed
- validate available audio

Candidate nodes:

- `InputSourceNode`
- `URLDetectNode`
- `MediaDownloadNode`
- `AudioExtractNode`
- `AudioValidateNode`

### Preprocessing Nodes

Purpose:

- prepare audio for stable analysis

Candidate nodes:

- `AudioLoadNode`
- `SNRGuardNode`
- `DenoiseNode`
- `LoudnessNormalizeNode`
- `PhaseAlignNode`
- `ChunkingNode`

### Analysis Nodes

Purpose:

- extract musical timing and reference information

Candidate nodes:

- `BeatNetNode`
- `LibrosaBeatNode`
- `BeatValidationNode`
- `DownbeatDetectNode`
- `MeasureMapNode`
- `KeyAnalysisNode`
- `ChordAnalysisNode`

### Export Nodes

Purpose:

- create assets for DAW, rehearsal, and PGM use

Candidate nodes:

- `ClickSynthesisNode`
- `ClickMixNode`
- `MIDIExportNode`
- `MidiClickGuideNode`
- `TempoPlotNode`
- `ReportJsonNode`
- `ReportTextNode`
- `ProjectPackageNode`

### AI Extension Nodes

Purpose:

- integrate optional model-based features without disturbing the MVP workflow

Candidate nodes:

- `StemSeparationNode`
- `InstrumentPresenceGuardNode`
- `MusicTranscriptionNode`
- `PitchTrackingNode`
- `SpeechTranscriptionNode`
- `SpeakerDiarizationNode`

These should remain optional until dependencies, model files, runtime requirements, and tests are ready.

## Guard And Fallback Strategy

Guard nodes check whether a branch should run.

Examples:

- audio is loud enough
- an instrument is likely present
- a model prerequisite is satisfied
- an optional dependency is installed

Fallback nodes provide alternatives.

Examples:

- BeatNet fails, then Librosa runs
- URL download fails, then user can upload local audio
- high-quality AI model is unavailable, then deterministic fallback runs

## Public Architecture Boundary

For the first formal release, the stable architectural boundary should be:

```text
Source Input -> Beat/Tempo Analysis -> DAW/PGM Export Package
```

AI separation and podcast workflows should be documented as extension branches until their implementations are real and tested.

## Current Implementation Map

| Area | Current Files | Current Status |
|------|---------------|----------------|
| GUI | `app.py` | Gradio app with downloader, stem, and PGM tabs |
| CLI | `pgm_craft/cli.py` | Runs main PGM pipeline |
| Pipeline | `pgm_craft/pipeline.py` | Orchestrates Behavior Tree result into report |
| BT Core | `pgm_craft/workflow/nodes.py` | Sequence, fallback, blackboard basics |
| BT Builder | `pgm_craft/workflow/builder.py` | Defines main workflow |
| Audio Nodes | `pgm_craft/workflow/audio_nodes.py` | Download, load, beat, analysis, export nodes |
| Analysis | `pgm_craft/analyzer.py` | BeatNet or Librosa, key and chord analysis |
| Export | `pgm_craft/synthesizer.py` | Click WAV and MIDI output |
| Stem Separation | `pgm_craft/separator.py` | Mostly placeholder copy-based implementation |
| AI Music | `pgm_craft/music_ai.py` | Experimental wrappers and fallbacks |
| Podcast | `pgm_craft/podcast_ai.py` | Placeholder outputs |
| Legacy | `main.py`, `web_app.py`, `beat_tracker.py` | Earlier standalone pipeline |

## Design Rule

When adding a new capability:

1. create or update one focused node
2. define required blackboard inputs
3. define blackboard outputs
4. add guard or fallback behavior if needed
5. connect it in the Behavior Tree
6. test the node and the workflow path
7. update this documentation
