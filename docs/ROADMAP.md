# Roadmap

**Last Updated:** 2026-07-22

This roadmap defines project phases. Each phase should produce a coherent, testable project state.

## Phase 0: Repository Baseline

Status: mostly complete.

Objectives:

- initialize Git version control
- ignore generated outputs and caches
- preserve test fixture audio
- document project goals and architecture
- separate public claims from implementation reality

Current notes:

- Git repository exists on local `main`
- first project snapshot was committed locally
- no GitHub remote is configured yet
- tests pass locally with warnings

## Phase 1: PGM And DAW Export MVP

Status: active target.

Objective:

Build a reliable workflow that turns audio into PGM and DAW-ready helper files.

Scope:

- local audio input
- URL input through downloader workflow
- audio loading and validation
- BeatNet beat tracking with Librosa fallback
- downbeat and measure mapping
- BPM statistics
- tempo curve plot
- click track WAV
- original plus click preview WAV
- `tempo_map.mid`
- initial `click_guide.mid` if split from tempo map
- JSON and text reports
- CLI and Gradio GUI execution

Exit criteria:

- tests cover the core pipeline
- generated outputs can be imported into a DAW
- README describes this as the stable feature set
- no local absolute paths remain in user-facing defaults

## Phase 2: Node Workflow Hardening

Status: planned.

Objective:

Make node execution explicit, testable, and reusable.

Scope:

- standard node input/output contract
- typed or documented blackboard keys
- node status handling
- workflow trace logging
- guard node conventions
- fallback node conventions
- error messages suitable for GUI and CLI
- unit tests for each major node

Exit criteria:

- developers can add a new node without changing unrelated pipeline code
- workflow execution can be inspected after a run
- failures show which node failed and why

## Phase 3: DAW Package Export

Status: planned.

Objective:

Move from individual output files to a DAW-ready project package.

Scope:

- output folder structure
- import guide per generated project
- tempo MIDI
- click guide MIDI
- click WAV
- preview WAV
- analysis JSON
- optional chord guide MIDI
- optional marker files
- future DAW profile abstraction

Example package:

```text
project-name/
├── audio/
│   ├── source.wav
│   ├── click_track.wav
│   └── mix_with_click.wav
├── midi/
│   ├── tempo_map.mid
│   └── click_guide.mid
├── reports/
│   ├── analysis_report.json
│   └── analysis_report.txt
└── IMPORT_GUIDE.md
```

Exit criteria:

- package layout is stable
- generated files have predictable names
- DAW import workflow is documented

## Phase 4: Public Release Cleanup

Status: planned.

Objective:

Prepare the project for GitHub public release.

Scope:

- rewrite README around actual MVP
- move experimental model claims into roadmap
- remove local machine paths
- clarify Python version support
- split core and optional dependencies
- add CI
- add contribution guidance
- add model/license notes
- decide whether to keep legacy root scripts or move them to `legacy/`

Exit criteria:

- fresh clone can install, run tests, and run the core workflow
- public claims match implementation
- optional AI features are clearly marked experimental

## Phase 5: AI-Assisted Music Modules

Status: future.

Objective:

Add real AI model integrations as optional nodes.

Candidate modules:

- stem separation
- Basic Pitch MIDI transcription
- CREPE pitch tracking
- instrument presence detection
- section detection
- podcast transcription and diarization

Exit criteria:

- model dependencies are optional
- model outputs are tested with fixtures or golden files
- fallback behavior is defined
- model licenses are documented
