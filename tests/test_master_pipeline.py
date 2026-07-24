"""
Unit tests for MasterBTWorkflowEngine (Master Behavior Tree Engine Pass 0 -> Pass 5)
"""

import os
import pytest
from pgm_craft.workflow.builder import MasterBTWorkflowEngine, build_master_pipeline_tree
from pgm_craft.workflow.nodes import NodeStatus


def test_build_master_pipeline_tree():
    tree = build_master_pipeline_tree()
    assert tree is not None
    assert tree.name == "MasterPGMPipelineRoot"


def test_master_bt_workflow_engine_instantiation():
    engine = MasterBTWorkflowEngine()
    assert engine.tree is not None
    assert engine.tree.name == "MasterPGMPipelineRoot"
