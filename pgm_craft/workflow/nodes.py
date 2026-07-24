"""
PGMCraft Behavior Tree (BT) & State Machine Workflow Core Engine.
"""

from enum import Enum, auto
import time

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


        blackboard.append_trace({
            "node": self.name,
            "node_type": self.__class__.__name__,
            "parent": parent,
            "status": status.name,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
        })
        return status

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


