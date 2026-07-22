"""
PGMCraft Behavior Tree (BT) & State Machine Workflow Core Engine.
"""

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


class BaseNode:
    """Abstract Base Class for Behavior Tree & State Machine Nodes."""
    def __init__(self, name="BaseNode"):
        self.name = name

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raise NotImplementedError


class SequenceNode(BaseNode):
    """Executes child nodes in order. Fails immediately if any child fails."""
    def __init__(self, name="Sequence", children=None):
        super().__init__(name)
        self.children = children if children else []

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        for child in self.children:
            status = child.execute(blackboard)
            if status != NodeStatus.SUCCESS:
                return status
        return NodeStatus.SUCCESS


class FallbackNode(BaseNode):
    """Executes child nodes in order until one succeeds (Selector / Fallback pattern)."""
    def __init__(self, name="Fallback", children=None):
        super().__init__(name)
        self.children = children if children else []

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        for child in self.children:
            status = child.execute(blackboard)
            if status == NodeStatus.SUCCESS:
                return NodeStatus.SUCCESS
        return NodeStatus.FAILURE
