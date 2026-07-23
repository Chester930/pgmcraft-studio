"""
PGMCraft Studio v2.0 Dynamic Behavior Tree Node Plugin Loader.
動態載入外部 plugins/ 目錄中繼承 BaseNode 的自訂處理節點。
"""

import os
import sys
import inspect
import importlib.util
from typing import Type
from pgm_craft.workflow.nodes import BaseNode

class PluginLoader:
    """外部插件探測與動態載入器。"""

    def __init__(self, plugin_dirs: list[str] = None):
        if plugin_dirs is None:
            plugin_dirs = ["plugins"]
        self.plugin_dirs = plugin_dirs

    def load_plugins(self) -> dict[str, Type[BaseNode]]:
        """掃描所有指定目錄，自動尋找並實體化 BaseNode 插件。"""
        discovered_nodes = {}
        for p_dir in self.plugin_dirs:
            if not os.path.exists(p_dir):
                continue

            for root, _, files in os.walk(p_dir):
                for file in files:
                    if file.endswith(".py") and not file.startswith("__"):
                        full_path = os.path.join(root, file)
                        nodes = self._load_nodes_from_file(full_path)
                        discovered_nodes.update(nodes)

        return discovered_nodes

    def _load_nodes_from_file(self, file_path: str) -> dict[str, Type[BaseNode]]:
        nodes = {}
        module_name = f"pgm_plugin_{os.path.splitext(os.path.basename(file_path))[0]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)

                for name, cls in inspect.getmembers(mod, inspect.isclass):
                    if issubclass(cls, BaseNode) and cls is not BaseNode:
                        nodes[name] = cls
        except Exception as exc:
            print(f"[PluginLoader] Failed to load plugin file {file_path}: {exc}")
        return nodes
