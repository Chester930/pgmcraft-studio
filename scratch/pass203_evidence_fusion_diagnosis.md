# PASS-203 Evidence Fusion Diagnosis

## Result

- Ticks: **500**; commits: **96**; no-candidate ticks: **402**; candidate-but-below-threshold ticks: **2**.
- Trace runtime: 4933.08s.
- Existing pipeline report: `SUCCESS`.
- Trace/report consistency: `{"trace_run_id": "d759f578-c8e9-4576-b61f-85894c93c2b7", "trace_tick_count": 500, "trace_commit_count": 96, "trace_last_committed_time": 171.736837, "artifact_committed_bar_count": 116, "artifact_last_committed_time": 175.774608, "artifact_run_id": "d759f578-c8e9-4576-b61f-85894c93c2b7", "production_state_consistency": {"run_id": "d759f578-c8e9-4576-b61f-85894c93c2b7", "committed_bar_starts_match_loop_report": false, "committed_bar_count": 116, "loop_report_committed_bar_count": 97, "last_committed_time": 175.774608, "loop_report_last_committed_time": 172.6909}}`.

## Evidence-source activity

("Candidate instances" counts a source as active whenever it either produced its own candidate or attached a support tag to someone else's -- e.g. bass/harmonic/phrase evidence is designed to boost a drum candidate's confidence rather than stand alone, so "standalone" can be 0 while the source is still working.)

| Source | Ticks with candidates | Candidate instances (incl. support tags) | Standalone candidates |
|---|---:|---:|---:|
| drum | 97 | 774 | 0 |
| drum_bass | 89 | 654 | 0 |
| chord | 79 | 186 | 0 |
| melody | 95 | 549 | 0 |
| v1_grid | 92 | 208 | 0 |
| beat_this | 0 | 0 | 0 |

## Decision classification

| Classification | Ticks |
|---|---:|
| all_candidates_already_committed | 1 |
| best_candidate_below_threshold | 2 |
| committed | 96 |
| no_upstream_candidates | 401 |

## Below-threshold gap

- Mean gap: 0.2900; minimum gap: 0.2500; maximum gap: 0.3300.
- Representative near-miss ticks:
  - tick 49: time=101.331882, confidence=0.45, threshold=0.7, sources=['drums', 'kick', 'exclusion_penalty', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 61: time=118.816508, confidence=0.37, threshold=0.7, sources=['drums', 'kick', 'exclusion_penalty', 'bass_coincidence_support']

## Interpretation

This report separates no-evidence ticks from near misses; it does not tune any confidence formula. Any follow-up parameter or source change requires a separate decision after reviewing these concrete examples.
