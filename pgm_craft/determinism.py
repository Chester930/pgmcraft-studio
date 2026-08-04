"""Reproducibility controls for BeatNet/Demucs (and any other neural) inference.

Neither BeatNet nor Demucs pins a random seed, and GPU inference is
non-deterministic by default in PyTorch: cuDNN's autotuner benchmarks several
convolution algorithms per input shape and picks whichever ran fastest *this
time*, so identical weights and identical input audio can still produce
slightly different outputs across runs. That run-to-run drift makes it
impossible to tell whether a code change actually improved the beat grid or
the pipeline just landed on a luckier random draw -- confirmed directly by
comparing three same-song, same-code runs whose `commercial_beat_quality`
scores drifted (88.71 / 88.47 / 89.3) despite v1's algorithm being untouched.

`enable_deterministic_mode()` pins every RNG source this pipeline touches and
switches PyTorch/cuDNN into their deterministic (if sometimes slower) modes,
so the same input audio run twice on the same machine produces the same
output. It does not change what the models predict -- only whether that
prediction is reproducible.
"""

import os
import random

_ALREADY_ENABLED = False


def enable_deterministic_mode(seed: int = 42) -> dict:
    """Pins RNG seeds and switches PyTorch to deterministic execution.

    Safe to call more than once (idempotent) and safe to call without a GPU
    or without PyTorch installed at all -- each step is best-effort and
    reports what it actually managed to apply.

    Must be called before any CUDA context exists for `CUBLAS_WORKSPACE_CONFIG`
    to take effect -- PyTorch requires this env var to be set prior to the
    first CUDA operation for deterministic cuBLAS (matmul) calls. This
    codebase only imports torch/BeatNet/Demucs lazily inside node `execute()`
    methods, so calling this at `PGMCraftEngine.__init__` (before any BT node
    has run) is early enough.
    """
    global _ALREADY_ENABLED

    report = {"seed": seed, "torch_available": False, "cuda_available": False, "applied": []}

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    report["applied"].append("CUBLAS_WORKSPACE_CONFIG")

    random.seed(seed)
    report["applied"].append("random.seed")

    try:
        import numpy as np
        np.random.seed(seed)
        report["applied"].append("numpy.random.seed")
    except ImportError:
        pass

    try:
        import torch
        report["torch_available"] = True

        torch.manual_seed(seed)
        report["applied"].append("torch.manual_seed")

        if torch.cuda.is_available():
            report["cuda_available"] = True
            torch.cuda.manual_seed_all(seed)
            report["applied"].append("torch.cuda.manual_seed_all")

        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        report["applied"].append("cudnn.deterministic+benchmark")

        # warn_only=True: a handful of ops have no deterministic GPU kernel;
        # failing outright on those would make this strictly worse than the
        # non-deterministic default for anyone who hits one. Falling back
        # to a slower deterministic path (or warning) is the practical choice.
        torch.use_deterministic_algorithms(True, warn_only=True)
        report["applied"].append("torch.use_deterministic_algorithms")
    except ImportError:
        pass

    _ALREADY_ENABLED = True
    report["status"] = "ENABLED"
    return report


def is_deterministic_mode_enabled() -> bool:
    return _ALREADY_ENABLED


def compare_beat_outputs(output1, output2, tolerance_sec: float = 1e-6) -> dict:
    """Pass 172: compare two beat-tracking outputs (e.g. two BeatNet runs on the
    same audio) and report whether they are reproducible.

    Used by scratch/pass172_beatnet_determinism_check.py to verify
    enable_deterministic_mode() actually makes Stage 3 beat tracking
    reproducible run-to-run, rather than assuming it does.
    """
    import numpy as np

    count1, count2 = len(output1), len(output2)
    count_match = count1 == count2

    max_delta = None
    if count_match and count1 > 0:
        arr1 = np.asarray(output1, dtype=float)
        arr2 = np.asarray(output2, dtype=float)
        max_delta = float(np.max(np.abs(arr1[:, 0] - arr2[:, 0])))

    if count_match and max_delta is not None and max_delta < tolerance_sec:
        verdict = "DETERMINISTIC"
    elif count_match:
        verdict = "MOSTLY_DETERMINISTIC"
    else:
        verdict = "NON_DETERMINISTIC"

    return {
        "count1": count1,
        "count2": count2,
        "count_match": count_match,
        "max_delta_sec": max_delta,
        "verdict": verdict,
    }
