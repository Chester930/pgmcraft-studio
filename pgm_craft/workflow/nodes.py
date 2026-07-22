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
            blackboard.append_trace({
                "node": self.name,
                "node_type": self.__class__.__name__,
                "parent": parent,
                "status": NodeStatus.FAILURE.name,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "error": str(exc),
            })
            raise

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
