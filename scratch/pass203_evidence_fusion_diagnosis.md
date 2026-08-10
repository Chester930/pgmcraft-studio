# PASS-203 Evidence Fusion Diagnosis

## Result

- Ticks: **500**; commits: **1**; no-candidate ticks: **481**; candidate-but-below-threshold ticks: **18**.
- Trace runtime: 813.09s.
- Existing pipeline report: `SUCCESS`.

## Evidence-source activity

("Candidate instances" counts a source as active whenever it either produced its own candidate or attached a support tag to someone else's -- e.g. bass/harmonic/phrase evidence is designed to boost a drum candidate's confidence rather than stand alone, so "standalone" can be 0 while the source is still working.)

| Source | Ticks with candidates | Candidate instances (incl. support tags) | Standalone candidates |
|---|---:|---:|---:|
| drum | 19 | 575 | 0 |
| drum_bass | 17 | 506 | 0 |
| chord | 18 | 106 | 0 |
| melody | 19 | 391 | 0 |
| v1_grid | 20 | 203 | 0 |
| beat_this | 0 | 0 | 0 |

## Below-threshold gap

- Mean gap: -0.1200; minimum gap: -0.3000; maximum gap: -0.0200.
- Representative near-miss ticks:
  - tick 3: time=12.376236, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'harmonic_anchor_support', 'phrase_anchor_support']
  - tick 14: time=112.41941, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'harmonic_anchor_support', 'phrase_anchor_support']
  - tick 15: time=135.604535, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 16: time=147.202902, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 2: time=6.616259, confidence=0.94, threshold=0.7, sources=['v1_grid', 'harmonic_anchor_support', 'phrase_anchor_support']

## Interpretation

This report separates no-evidence ticks from near misses; it does not tune any confidence formula. Any follow-up parameter or source change requires a separate decision after reviewing these concrete examples.
