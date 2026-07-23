"""
PGMCraft Workflow Blackboard Context & Contract Specifications.
Defines typed key contracts for Behavior Tree workflow execution.
"""

from typing import Dict, Any, List, Optional, TypedDict


class WorkflowEntryContext(TypedDict, total=False):
    audio_path: str
    output_dir: str
    enable_stem: bool
    demix_steps: List[str]
    validate_contracts: bool


class TimingContext(TypedDict, total=False):
    beats: Any
    beat_validation: Dict[str, Any]
    beat_confidence_level: str
    beat_warnings: List[str]
    beat_errors: List[str]
    refined_beats: Any
    downbeat_refinement: Dict[str, Any]
    downbeat_refine_status: str
    downbeat_refine_warnings: List[str]
    downbeat_candidates: List[Dict[str, Any]]
    measure_map: List[Dict[str, Any]]
    measure_map_status: str
    measure_map_warnings: List[str]


class MusicReferenceContext(TypedDict, total=False):
    estimated_key: str
    chord_progression: List[Dict[str, Any]]


class ExportContext(TypedDict, total=False):
    click_track: str
    mix_with_click: str
    tempo_map_midi: str
    click_guide_midi: str
    chord_guide_midi: Optional[str]


KNOWN_CONTRACT_KEYS: Dict[str, type] = {
    "audio_path": str,
    "output_dir": str,
    "enable_stem": bool,
    "validate_contracts": bool,
    "beat_confidence_level": str,
    "beat_warnings": list,
    "beat_errors": list,
    "downbeat_refine_status": str,
    "downbeat_refine_warnings": list,
    "measure_map_status": str,
    "measure_map_warnings": list,
    "estimated_key": str,
    "chord_progression": list,
    "click_track": str,
    "mix_with_click": str,
    "tempo_map_midi": str,
    "click_guide_midi": str,
    "chord_guide_midi": str,
}
