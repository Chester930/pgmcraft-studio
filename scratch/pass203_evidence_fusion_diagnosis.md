# PASS-203 Evidence Fusion Diagnosis

## Result

- Ticks: **9**; commits: **5**; no-candidate ticks: **0**; candidate-but-below-threshold ticks: **4**.
- Trace runtime: 792.04s.
- Existing pipeline report: `SUCCESS`.

## Evidence-source activity

| Source | Ticks with candidates | Candidate instances |
|---|---:|---:|
| drum | 9 | 133 |
| drum_bass | 0 | 0 |
| chord | 0 | 0 |
| melody | 0 | 0 |
| v1_grid | 9 | 53 |
| beat_this | 0 | 0 |

## Below-threshold gap

- Mean gap: 0.1375; minimum gap: 0.1000; maximum gap: 0.2500.
- Representative near-miss ticks:
  - tick 7: time=34.017234, confidence=0.6, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'exclusion_penalty', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 8: time=38.359365, confidence=0.6, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'exclusion_penalty', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 9: time=48.471655, confidence=0.6, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'exclusion_penalty', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 1: time=2.902494, confidence=0.45, threshold=0.7, sources=['drums', 'drum_onset', 'outside_fill_exclusion']

## Interpretation

This report separates no-evidence ticks from near misses; it does not tune any confidence formula. Any follow-up parameter or source change requires a separate decision after reviewing these concrete examples.
