"""
PGMCraft Stage 0 — Input Acquisition Behavior Tree.

Two input paths (URL / local file) converge to a unified project structure:
  {project_root}/{project_name}/
    source/   <- normalised WAV
    stems/
    click/
    midi/
    reports/

Blackboard output contract (guaranteed after SUCCESS):
  audio_path      -> {project_dir}/source/{name}.wav
  project_dir     -> {project_root}/{project_name}/
  project_name    -> str
  media_title     -> str (same as project_name)
  source_type     -> "url" | "local_file"
  original_url    -> str  (url path only)
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.workflow.nodes import SequenceNode, FallbackNode
from pgm_craft.workflow.downloaders import URLDownloaderDispatcher


SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"}


# ---------------------------------------------------------------------------
# Guard Nodes
# ---------------------------------------------------------------------------

class ValidateInputNode(BaseNode):
    """Guard: ensure url or audio_path is provided.

    url takes priority; if set, overwrites audio_path on the blackboard.
    """
    required_keys = []
    optional_keys = ["url", "audio_path"]
    output_keys = ["audio_path"]

    def __init__(self):
        super().__init__("ValidateInputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        url = (blackboard.get_val("url") or "").strip()
        audio_path = (blackboard.get_val("audio_path") or "").strip()

        if url:
            blackboard.set_val("audio_path", url)
            print(f"[ValidateInput] URL input: {url}")
            return NodeStatus.SUCCESS

        if audio_path:
            print(f"[ValidateInput] local file input: {audio_path}")
            return NodeStatus.SUCCESS

        print("[ValidateInput] ERROR: no input provided (url and audio_path both empty)")
        return NodeStatus.FAILURE


class ValidateProjectRootNode(BaseNode):
    """Guard: ensure project_root exists and is writable."""
    required_keys = ["project_root"]
    optional_keys = []
    output_keys = ["project_root_validated"]

    def __init__(self):
        super().__init__("ValidateProjectRootNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        root = (blackboard.get_val("project_root") or "").strip()
        if not root:
            print("[ValidateProjectRoot] ERROR: project_root not set")
            return NodeStatus.FAILURE
        try:
            os.makedirs(root, exist_ok=True)
            probe = os.path.join(root, ".pgmcraft_probe")
            open(probe, "w").close()
            os.remove(probe)
        except Exception as exc:
            print(f"[ValidateProjectRoot] ERROR not writable: {exc}")
            return NodeStatus.FAILURE
        print(f"[ValidateProjectRoot] OK: {root}")
        blackboard.set_val("project_root_validated", True)
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Condition Nodes
# ---------------------------------------------------------------------------

class IsURLConditionNode(BaseNode):
    """Condition: audio_path starts with http/https."""
    required_keys = ["audio_path"]
    optional_keys = []
    output_keys = ["is_url_checked"]

    def __init__(self):
        super().__init__("IsURLConditionNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        src = blackboard.get_val("audio_path", "")
        res = NodeStatus.SUCCESS if re.match(r'^https?://', src.strip()) else NodeStatus.FAILURE
        if res == NodeStatus.SUCCESS:
            blackboard.set_val("is_url_checked", True)
        return res


class IsLocalFileConditionNode(BaseNode):
    """Condition: audio_path is an existing local file."""
    required_keys = ["audio_path"]
    optional_keys = []
    output_keys = ["is_local_file_checked"]

    def __init__(self):
        super().__init__("IsLocalFileConditionNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        src = blackboard.get_val("audio_path", "")
        if src and os.path.isfile(src):
            blackboard.set_val("is_local_file_checked", True)
            return NodeStatus.SUCCESS
        print(f"[IsLocalFile] not found: {src}")
        return NodeStatus.FAILURE


# ---------------------------------------------------------------------------
# Action Nodes — URL branch
# ---------------------------------------------------------------------------

class URLDownloadToTempNode(BaseNode):
    """Download URL via URLDownloaderDispatcher into a temp subfolder.

    Writes: raw_wav_path, media_title, source_type="url", original_url,
    plus raw_mp3_path/raw_mp4_path when the handler produced them (the main
    pipeline only consumes raw_wav_path; the extra formats exist so this
    single node can also serve the standalone download tab, which needs
    all three -- see app.py's standalone_download()).
    """
    required_keys = ["audio_path", "project_root"]
    optional_keys = []
    output_keys = [
        "raw_wav_path", "raw_mp3_path", "raw_mp4_path",
        "media_title", "source_type", "original_url",
    ]

    def __init__(self):
        super().__init__("URLDownloadToTempNode")
        self.dispatcher = URLDownloaderDispatcher()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        url = blackboard.get_val("audio_path")
        project_root = blackboard.get_val("project_root")
        temp_dir = os.path.join(project_root, "_pgmcraft_temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)

        print(f"[URLDownload] downloading: {url}")
        try:
            result = self.dispatcher.dispatch_and_download(url, temp_dir)
        except Exception as exc:
            print(f"[URLDownload] FAILED: {exc}")
            return NodeStatus.FAILURE

        wav_path = result.get("wav")
        mp3_path = result.get("mp3")
        mp4_path = result.get("mp4")
        title = result.get("title", "untitled")

        if not wav_path or not os.path.exists(wav_path):
            print("[URLDownload] WAV missing after download")
            return NodeStatus.FAILURE

        blackboard.set_val("raw_wav_path", wav_path)
        blackboard.set_val("raw_mp3_path", mp3_path if mp3_path and os.path.exists(mp3_path) else None)
        blackboard.set_val("raw_mp4_path", mp4_path if mp4_path and os.path.exists(mp4_path) else None)
        blackboard.set_val("media_title", title)
        blackboard.set_val("source_type", "url")
        blackboard.set_val("original_url", url)
        print(f"[URLDownload] OK wav={wav_path} title={title}")
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Action Nodes — local file branch
# ---------------------------------------------------------------------------

class ValidateAudioFileNode(BaseNode):
    """Guard: check extension; write raw_wav_path / media_title / source_type."""
    required_keys = ["audio_path"]
    optional_keys = []
    output_keys = ["raw_wav_path", "media_title", "source_type"]

    def __init__(self):
        super().__init__("ValidateAudioFileNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        path = blackboard.get_val("audio_path")
        ext = Path(path).suffix.lower()
        if ext not in SUPPORTED_AUDIO_EXTENSIONS:
            print(f"[ValidateAudioFile] unsupported format: {ext}")
            return NodeStatus.FAILURE
        title = Path(path).stem
        blackboard.set_val("raw_wav_path", path)
        blackboard.set_val("media_title", title)
        blackboard.set_val("source_type", "local_file")
        print(f"[ValidateAudioFile] OK ext={ext} title={title}")
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Convergence Node
# ---------------------------------------------------------------------------

class NormalizeToProjectWAVNode(BaseNode):
    """Normalise raw audio to a standard WAV.

    Strategy:
      1. If already WAV with samplerate >= 22050 => use as-is.
      2. Otherwise => ffmpeg convert to target_sr / 16-bit / stereo.
      3. ffmpeg not found => librosa + soundfile fallback.

    Writes: normalized_wav_path
    """
    required_keys = ["raw_wav_path", "media_title"]
    optional_keys = []
    output_keys = ["normalized_wav_path"]

    def __init__(self, target_sr: int = 44100):
        super().__init__("NormalizeToProjectWAVNode")
        self.target_sr = target_sr

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raw = blackboard.get_val("raw_wav_path")
        title = blackboard.get_val("media_title", "untitled")
        ext = Path(raw).suffix.lower()
        out_dir = os.path.dirname(raw)
        out_wav = os.path.join(out_dir, f"{title}_normalized.wav")

        # Fast-path: already a usable WAV
        if ext == ".wav":
            try:
                import soundfile as sf
                info = sf.info(raw)
                if info.samplerate >= 22050:
                    blackboard.set_val("normalized_wav_path", raw)
                    print(f"[NormalizeWAV] reuse existing WAV sr={info.samplerate}")
                    return NodeStatus.SUCCESS
            except Exception:
                pass  # soundfile unavailable — fall through to ffmpeg

        # ffmpeg convert
        try:
            cmd = [
                "ffmpeg", "-y", "-i", raw,
                "-ar", str(self.target_sr),
                "-sample_fmt", "s16",
                "-ac", "2",
                out_wav,
            ]
            proc = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.decode(errors="replace"))
        except FileNotFoundError:
            print("[NormalizeWAV] ffmpeg not found; using librosa fallback")
            try:
                import librosa
                import soundfile as sf
                y, _ = librosa.load(raw, sr=self.target_sr, mono=False)
                if y.ndim == 1:
                    y = y[None, :]
                sf.write(out_wav, y.T, self.target_sr, subtype="PCM_16")
            except Exception as exc:
                print(f"[NormalizeWAV] librosa fallback FAILED: {exc}")
                return NodeStatus.FAILURE
        except Exception as exc:
            print(f"[NormalizeWAV] ffmpeg error: {exc}")
            return NodeStatus.FAILURE

        if not os.path.exists(out_wav):
            print("[NormalizeWAV] output file missing after conversion")
            return NodeStatus.FAILURE

        blackboard.set_val("normalized_wav_path", out_wav)
        print(f"[NormalizeWAV] OK: {out_wav}")
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Project Setup Chain
# ---------------------------------------------------------------------------

class ResolveProjectNameNode(BaseNode):
    """Derive a filesystem-safe project name from media_title."""
    required_keys = ["media_title"]
    optional_keys = []
    output_keys = ["project_name"]

    def __init__(self):
        super().__init__("ResolveProjectNameNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        title = blackboard.get_val("media_title", "untitled")
        safe = re.sub(r'[\\/*?:"<>|]', "", title).strip()
        safe = re.sub(r'\s+', "_", safe)
        safe = safe[:120] or "untitled_project"
        blackboard.set_val("project_name", safe)
        print(f"[ResolveProjectName] -> {safe}")
        return NodeStatus.SUCCESS


class CreateProjectFolderNode(BaseNode):
    """Create {project_root}/{project_name}/ with standard subdirectories."""
    required_keys = ["project_root", "project_name"]
    optional_keys = []
    output_keys = ["project_dir"]

    SUBDIRS = ["source", "stems", "click", "midi", "reports"]

    def __init__(self):
        super().__init__("CreateProjectFolderNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        root = blackboard.get_val("project_root")
        name = blackboard.get_val("project_name")
        project_dir = os.path.join(root, name)
        try:
            for sub in self.SUBDIRS:
                os.makedirs(os.path.join(project_dir, sub), exist_ok=True)
        except Exception as exc:
            print(f"[CreateProjectFolder] FAILED: {exc}")
            return NodeStatus.FAILURE
        blackboard.set_val("project_dir", project_dir)
        print(f"[CreateProjectFolder] OK: {project_dir}")
        return NodeStatus.SUCCESS


class CopySourceToProjectNode(BaseNode):
    """Copy normalized WAV to {project_dir}/source/{project_name}.wav; update audio_path."""
    required_keys = ["normalized_wav_path", "project_dir", "project_name"]
    optional_keys = []
    output_keys = ["audio_path"]

    def __init__(self):
        super().__init__("CopySourceToProjectNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        src = blackboard.get_val("normalized_wav_path")
        project_dir = blackboard.get_val("project_dir")
        name = blackboard.get_val("project_name")
        dest = os.path.join(project_dir, "source", f"{name}.wav")
        try:
            shutil.copy2(src, dest)
        except Exception as exc:
            print(f"[CopySource] FAILED: {exc}")
            return NodeStatus.FAILURE
        blackboard.set_val("audio_path", dest)
        print(f"[CopySource] OK: {dest}")
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Tree Builder & Engine
# ---------------------------------------------------------------------------

def build_input_acquisition_tree() -> SequenceNode:
    """Build the Stage 0 Input Acquisition Behavior Tree.

    Sequence [InputAcquisitionRoot]
    ├── ValidateInputNode
    ├── ValidateProjectRootNode
    ├── Fallback [InputSourceSelector]
    │   ├── Sequence [URLInputBranch]
    │   │   ├── IsURLConditionNode
    │   │   ├── URLDownloadToTempNode
    │   │   └── NormalizeToProjectWAVNode
    │   └── Sequence [LocalFileInputBranch]
    │       ├── IsLocalFileConditionNode
    │       ├── ValidateAudioFileNode
    │       └── NormalizeToProjectWAVNode
    └── Sequence [ProjectSetupChain]
        ├── ResolveProjectNameNode
        ├── CreateProjectFolderNode
        └── CopySourceToProjectNode
    """
    url_branch = SequenceNode("URLInputBranch", [
        IsURLConditionNode(),
        URLDownloadToTempNode(),
        NormalizeToProjectWAVNode(),
    ])

    local_branch = SequenceNode("LocalFileInputBranch", [
        IsLocalFileConditionNode(),
        ValidateAudioFileNode(),
        NormalizeToProjectWAVNode(),
    ])

    source_selector = FallbackNode("InputSourceSelector", [url_branch, local_branch])

    project_setup = SequenceNode("ProjectSetupChain", [
        ResolveProjectNameNode(),
        CreateProjectFolderNode(),
        CopySourceToProjectNode(),
    ])

    return SequenceNode("InputAcquisitionRoot", [
        ValidateInputNode(),
        ValidateProjectRootNode(),
        source_selector,
        project_setup,
    ])


class InputAcquisitionBTEngine:
    """Stage 0 Behavior Tree Engine wrapper."""

    def __init__(self):
        self.tree = build_input_acquisition_tree()

    def run(
        self,
        *,
        audio_path: str = "",
        url: str = "",
        project_root: str = "outputs",
    ) -> Blackboard:
        bb = Blackboard()
        bb.set_val("audio_path", audio_path)
        bb.set_val("url", url)
        bb.set_val("project_root", project_root)

        print("\n=== [InputAcquisitionBT] Stage 0 Start ===")
        status = self.tree.run(bb)
        bb.set_val("input_acquisition_status", status.name)

        if status.name == "SUCCESS":
            print(f"=== [InputAcquisitionBT] Done: {bb.get_val('project_dir')} ===")
        else:
            print("=== [InputAcquisitionBT] FAILED ===")

        return bb
