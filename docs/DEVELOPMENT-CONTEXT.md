# Development Context

**Last Updated:** 2026-07-22

This file records the project context as of the first formal documentation pass.

## Current Repository State

- Local Git repository exists.
- Current branch is `main`.
- Initial local commit exists: `029d072 chore: initial project snapshot`.
- No GitHub remote is configured.
- GitHub CLI is authenticated as `Chester930`.
- A GitHub repository matching this project was not found in the queried repo list.

## Current Test State

Latest observed command:

```bash
python -m pytest -q
```

Latest observed result:

```text
28 passed, 1 skipped
```

Warnings observed:

- Python 3.13 audio-related deprecation warnings from `audioread`
- `requests` dependency warning about urllib3 or charset package version compatibility

## Important Implementation Reality

The current repository contains both working MVP pieces and future-facing placeholders.

Working or mostly working areas:

- local audio analysis
- BeatNet with Librosa fallback
- key and chord reference analysis
- click track WAV synthesis
- mix with click WAV output
- MIDI output
- tempo curve plot
- JSON report
- Gradio GUI shell
- CLI shell

Placeholder or experimental areas:

- most stem separation functions currently copy files instead of running real separation models
- podcast diarization and enhancement write placeholder outputs
- some music AI functions return fixed sample data or fallback minimal files
- advanced model registry is a roadmap structure, not proof of installed model support

This distinction must remain visible in public documentation.

## Current Architectural Direction

The project direction discussed and accepted in working conversation:

- The primary project goal is DAW and PGM asset generation from audio.
- DAW-importable MIDI output is a core product feature.
- The system should be designed as a node-based audio workflow.
- Behavior Tree orchestration should coordinate nodes, guard conditions, and fallbacks.
- AI stem separation and podcast workflows should remain extension modules until implemented for real.

## Public Release Cleanup Needed

Before making the repository public:

- rewrite README to match the real MVP
- remove `your-username` clone placeholder
- remove local absolute paths from GUI defaults
- avoid broad filesystem `allowed_paths` defaults in public GUI code
- clarify implemented features versus roadmap features
- split core dependencies from optional AI/downloader dependencies
- decide whether `main.py`, `web_app.py`, and `beat_tracker.py` are legacy examples or supported entry points
- add CI
- add documentation for generated DAW package import

## Existing Dirty Working Tree Note

At the time this documentation pass started, `app.py` already showed local modifications. This documentation pass should not assume ownership of those changes.

When committing documentation, review `git diff` and avoid mixing unrelated `app.py` changes unless intentionally included.

## Suggested Formal ADRs

The following architectural decisions are important enough to record as ADRs if the project adopts an ADR process:

- Use node-based workflow plus Behavior Tree orchestration.
- Define DAW-ready export package as the project core instead of AI stem separation.
- Treat AI model integrations as optional extension nodes until fully implemented.
- Keep BeatNet as preferred beat tracker and Librosa as deterministic fallback.

If ADRs are adopted, create `docs/adr/` with an index and one ADR per decision.
