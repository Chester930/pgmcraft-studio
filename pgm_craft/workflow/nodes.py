"""
PGMCraft Behavior Tree (BT) & State Machine Workflow Core Engine.
"""

import os
import time
from enum import Enum, auto

class NodeStatus(Enum):
    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()

class Blackboard(dict):
    """Shared execution context / state passed across workflow nodes."""
    def get_val(self, key, default=None):
        return self.get(key, default)
    
    def set_val(self, key, value):
        self[key] = value

    def get_typed(self, key, expected_type, default=None):
        """Retrieves value with type safety check."""
        val = self.get(key, default)
        if val is not None and not isinstance(val, expected_type):
            try:
                return expected_type(val)
            except (ValueError, TypeError):
                return default
        return val

    def validate_strict(self, node) -> list:
        """Validates node required keys and returns list of missing keys."""
        missing = [key for key in getattr(node, "required_keys", []) if key not in self]
        return missing

    def append_trace(self, entry):
        trace = self.setdefault("workflow_trace", [])
        entry["index"] = len(trace)
        trace.append(entry)

    def append_contract_validation(self, entry):
        validations = self.setdefault("contract_validation", [])
        entry["index"] = len(validations)
        validations.append(entry)

    def get_audio_hash(self) -> str:
        """Retrieves or calculates SHA256 hash (first 16 chars) for current audio_path."""
        if "audio_hash" in self:
            return self["audio_hash"]
        audio_path = self.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            return "default_hash"
        import hashlib
        hasher = hashlib.sha256()
        with open(audio_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        h = hasher.hexdigest()[:16]
        self["audio_hash"] = h
        return h

    def get_cached_artifact(self, cache_key: str):
        """Reads JSON cached artifact from ./cache/{audio_hash}/{cache_key}.json if present."""
        import json
        h = self.get_audio_hash()
        cache_dir = os.path.join("cache", h)
        cache_file = os.path.join(cache_dir, f"{cache_key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def set_cached_artifact(self, cache_key: str, data: dict):
        """Writes JSON artifact to ./cache/{audio_hash}/{cache_key}.json."""
        import json
        h = self.get_audio_hash()
        cache_dir = os.path.join("cache", h)
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{cache_key}.json")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Blackboard Cache] ⚠️ Write cache failed: {e}")

    def get_telemetry_report(self) -> dict:
        """Generates performance telemetry and profiler report for executed nodes."""
        trace = self.get("workflow_trace", [])
        total_ms = sum(entry.get("duration_ms", 0.0) for entry in trace)
        return {
            "total_execution_time_ms": round(total_ms, 3),
            "total_nodes_executed": len(trace),
            "node_metrics": [
                {
                    "node": entry.get("node"),
                    "node_type": entry.get("node_type"),
                    "duration_ms": entry.get("duration_ms"),
                    "status": entry.get("status")
                }
                for entry in trace
            ]
        }



class BaseNode:
    """Abstract Base Class for Behavior Tree & State Machine Nodes."""
    required_keys = []
    optional_keys = []
    output_keys = []

    def __init__(self, name="BaseNode"):
        self.name = name

    def run(self, blackboard: Blackboard, parent=None) -> NodeStatus:
        """Executes a node and records one workflow trace entry."""
        if blackboard.get_val("validate_contracts", False):
            blackboard.append_contract_validation(self.validate_contract(blackboard, parent=parent))

        started_at = time.perf_counter()
        try:
            status = self.execute(blackboard)
        except Exception as exc:
            print(f"[BT Self-Healing Guard: {self.name}] 成功攔截節點執行異常 ({exc}) ➔ 安全降級為 FAILURE 引導 Fallback 替代路徑！")
            blackboard.append_trace({
                "node": self.name,
                "node_type": self.__class__.__name__,
                "parent": parent,
                "status": NodeStatus.FAILURE.name,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "error": str(exc),
            })
            return NodeStatus.FAILURE


        status_val = status.name if isinstance(status, NodeStatus) else NodeStatus.SUCCESS.name
        blackboard.append_trace({
            "node": self.name,
            "node_type": self.__class__.__name__,
            "parent": parent,
            "status": status_val,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
        })
        return status if isinstance(status, NodeStatus) else NodeStatus.SUCCESS

    def validate_contract(self, blackboard: Blackboard, parent=None):
        missing_required_keys = [
            key for key in self.required_keys
            if key not in blackboard
        ]
        return {
            "node": self.name,
            "node_type": self.__class__.__name__,
            "parent": parent,
            "status": "WARN" if missing_required_keys else "PASS",
            "missing_required_keys": missing_required_keys,
            "required_keys": list(self.required_keys),
            "optional_keys": list(self.optional_keys),
            "output_keys": list(self.output_keys),
        }

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raise NotImplementedError


class SequenceNode(BaseNode):
    """Executes child nodes in order. Fails immediately if any child fails."""
    output_keys = ["workflow_trace"]

    def __init__(self, name="Sequence", children=None):
        super().__init__(name)
        self.children = children if children else []

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        for child in self.children:
            status = child.run(blackboard, parent=self.name)
            if status != NodeStatus.SUCCESS:
                return status
        return NodeStatus.SUCCESS


class FallbackNode(BaseNode):
    """Executes child nodes in order until one succeeds (Selector / Fallback pattern)."""
    output_keys = ["workflow_trace"]

    def __init__(self, name="Fallback", children=None):
        super().__init__(name)
        self.children = children if children else []

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        for child in self.children:
            status = child.run(blackboard, parent=self.name)
            if status == NodeStatus.SUCCESS:
                return NodeStatus.SUCCESS
        return NodeStatus.FAILURE


class RetryFallbackNode(BaseNode):
    """Decorator node: retries a child node up to max_retries times.
    
    If all retries fail and a fallback node is provided, runs the fallback.
    Provides resilience for network-dependent or AI-inference nodes.
    """

    def __init__(self, name="RetryFallback", child=None, max_retries=2, fallback=None):
        super().__init__(name)
        self.child = child
        self.max_retries = max_retries
        self.fallback = fallback

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        attempts = 1 + self.max_retries
        for attempt in range(attempts):
            status = self.child.run(blackboard, parent=self.name)
            if status == NodeStatus.SUCCESS:
                return NodeStatus.SUCCESS

        # All retries exhausted — activate fallback if available
        if self.fallback is not None:
            return self.fallback.run(blackboard, parent=self.name)

        return NodeStatus.FAILURE


class ParallelNode(BaseNode):
    """Executes all children concurrently using a thread pool.

    Args:
        children: List of child nodes to execute in parallel.
        success_threshold: Number of children that must succeed for ParallelNode
            to return SUCCESS. Defaults to len(children) (all must succeed).
        max_workers: Maximum number of worker threads. Defaults to len(children).
    """

    def __init__(self, name="Parallel", children=None, success_threshold=None, max_workers=None):
        super().__init__(name)
        self.children = children if children else []
        self.success_threshold = success_threshold if success_threshold is not None else len(self.children)
        self.max_workers = max_workers or max(1, len(self.children))
        # Aggregate output_keys from all children
        self.output_keys = list({k for child in self.children for k in getattr(child, "output_keys", [])})


    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if not self.children:
            return NodeStatus.SUCCESS

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def run_child(child):
            return child.name, child.run(blackboard, parent=self.name)

        successes = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(run_child, child): child for child in self.children}
            for future in as_completed(futures):
                _, status = future.result()
                if status == NodeStatus.SUCCESS:
                    successes += 1

        return NodeStatus.SUCCESS if successes >= self.success_threshold else NodeStatus.FAILURE


