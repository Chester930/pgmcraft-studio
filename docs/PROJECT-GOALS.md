# Project Goals

**Last Updated:** 2026-07-22

## Project Definition

PGMCraft Studio is a node-based audio workflow system for musicians, arrangers, live-performance preparation, and DAW project setup.

The core goal is to transform an audio or video source into a DAW-ready project asset package, including beat timing, tempo information, click tracks, MIDI guide files, analysis reports, and future AI-assisted transcription or separation outputs.

## Primary Users

- musicians preparing practice or rehearsal material
- arrangers and producers preparing DAW sessions
- live-performance operators preparing PGM and click tracks
- transcription users who need beat, tempo, key, and chord references
- future users who need AI stem separation or podcast audio preprocessing

## Core Product Promise

Given a local audio file or supported media URL, PGMCraft Studio should produce a project folder that can be used directly in a music workflow.

The first stable version should reliably provide:

- source audio preparation
- beat and downbeat detection
- BPM statistics and tempo curve
- click track WAV
- original audio plus click preview WAV
- DAW-importable MIDI guide output
- basic key and chord reference
- JSON and text reports
- CLI and GUI entry points

## DAW-Ready Export Goal

DAW export is a core feature, not a side output.

The project should move from a simple MIDI file toward a DAW-ready asset package:

- `tempo_map.mid` for tempo and timing reference
- `click_guide.mid` for per-beat MIDI click notes
- future bar, section, and chord guide tracks
- future DAW profiles for Ableton Live, Logic Pro, Cubase, Reaper, and other tools
- packaged output folder with clear import instructions

## Architecture Goal

The project is designed around:

- small audio-processing nodes
- shared workflow state through a blackboard
- Behavior Tree orchestration
- fallback paths for unreliable or optional models
- guard nodes for prerequisites and safety checks

This keeps the project extensible: future AI models can be added as nodes without rewriting the whole workflow.

## Non-Goals For The First Public Version

The first public version should not claim production-grade support for features that are currently stubs or experimental.

Do not present these as completed unless the implementation is actually integrated and tested:

- real BS-Roformer, UVR, or Demucs stem separation quality
- lead/backing vocal separation
- drum sub-stem separation
- full Whisper or pyannote podcast pipeline
- Basic Pitch or CREPE production workflows
- automatic section recognition
- DAW-specific project file generation

These belong in the roadmap until they are implemented and verified.

## Success Criteria

The project is moving in the right direction when:

- a user can import generated MIDI and WAV assets into a DAW
- beat and click outputs are stable enough for rehearsal preparation
- each workflow capability is represented as a clear node
- Behavior Tree structure explains why each step runs or falls back
- documentation distinguishes implemented features from planned features
- tests protect the core audio-to-project-package flow
