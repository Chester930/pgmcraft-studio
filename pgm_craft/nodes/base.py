"""
PGMCraft Node Graph Base Architecture
Defines Node, Pin, and NodeGraph execution framework.
"""

from typing import Dict, Any, List

class Pin:
    def __init__(self, name: str, data_type: type):
        self.name = name
        self.data_type = data_type
        self.value = None

class Node:
    node_type = "BaseNode"

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.inputs: Dict[str, Pin] = {}
        self.outputs: Dict[str, Pin] = {}

    def add_input(self, name: str, data_type: type, default=None):
        pin = Pin(name, data_type)
        pin.value = default
        self.inputs[name] = pin

    def add_output(self, name: str, data_type: type):
        pin = Pin(name, data_type)
        self.outputs[name] = pin

    def execute(self, context: Dict[str, Any]):
        raise NotImplementedError
