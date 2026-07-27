"""
Stage 6: Package & DAW Material Handoff Behavior Tree (PackageRoot)
"""

import os
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, SequenceNode
from pgm_craft.packager import PGMProjectPackager
from pgm_craft.daw_exporter import DAWExporter, DAWProfileRegistry

class DAWSessionGenerateNode(BaseNode):
    """生成 Reaper, Ableton Live, Logic Pro, Cubase 專案工程與 Marker CSV"""
    required_keys = ["output_dir"]
    output_keys = ["outputs"]

    def execute(self, blackboard) -> NodeStatus:
        output_dir = blackboard.get_val("output_dir", "outputs")
        report = dict(blackboard)
        
        package_dir = os.path.join(output_dir, PGMProjectPackager.PACKAGE_DIR_NAME)
        os.makedirs(package_dir, exist_ok=True)
        
        registry = DAWProfileRegistry()
        daw_files = registry.export_profile("all", report, output_dir=package_dir)
        
        daw_exporter = DAWExporter()
        als_path = daw_exporter.generate_ableton_als(report, output_dir=package_dir)
        csv_path = daw_exporter.export_marker_csv(
            report.get("chord_progression", []),
            sections=report.get("sections", []),
            output_dir=package_dir
        )
        aaf_path = daw_exporter.export_aaf_project(report, output_dir=package_dir)
        
        outputs = blackboard.get_val("outputs", {})
        outputs.update(daw_files)
        outputs["ableton_project"] = als_path
        outputs["markers_csv"] = csv_path
        outputs["aaf_project"] = aaf_path
        blackboard.set_val("outputs", outputs)
        
        print(f"[DAWSessionGenerateNode] ✅ 成功生成 DAW 專案檔 (Reaper/Ableton/Logic/Cubase CSV Marker) ➔ {package_dir}")
        return NodeStatus.SUCCESS


class LiveDashboardExportNode(BaseNode):
    """生成 Live 舞台團員螢幕用的對拍與樂段 HTML 儀表板"""
    required_keys = ["output_dir"]
    output_keys = ["outputs"]

    def execute(self, blackboard) -> NodeStatus:
        output_dir = blackboard.get_val("output_dir", "outputs")
        report = dict(blackboard)
        
        package_dir = os.path.join(output_dir, PGMProjectPackager.PACKAGE_DIR_NAME)
        reports_dir = os.path.join(package_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        daw_exporter = DAWExporter()
        dash_path = daw_exporter.generate_live_dashboard_html(report, output_dir=reports_dir)
        
        outputs = blackboard.get_val("outputs", {})
        outputs["live_dashboard"] = dash_path
        blackboard.set_val("outputs", outputs)
        
        print(f"[LiveDashboardExportNode] ✅ 成功匯出 Live 舞台 HTML 儀表板 ➔ {os.path.basename(dash_path)}")
        return NodeStatus.SUCCESS


class ZIPArchivePackagerNode(BaseNode):
    """執行 PGMProjectPackager 打包 pgm_project_package/ 並壓縮生成 .zip 素材包"""
    required_keys = ["output_dir"]
    output_keys = ["project_package", "outputs"]

    def execute(self, blackboard) -> NodeStatus:
        output_dir = blackboard.get_val("output_dir", "outputs")
        report = dict(blackboard)
        
        packager = PGMProjectPackager()
        project_package = packager.build(report, output_dir=output_dir)
        
        blackboard.set_val("project_package", project_package)
        
        outputs = blackboard.get_val("outputs", {})
        outputs["zip_archive"] = project_package.get("zip_archive", "")
        outputs["project_package_dir"] = project_package.get("project_package_dir", "")
        outputs["import_guide"] = project_package.get("import_guide", "")
        blackboard.set_val("outputs", outputs)
        
        print(f"[ZIPArchivePackagerNode] 🎉 Stage 6 全套 DAW 工程素材包打包完畢: {os.path.basename(project_package.get('zip_archive', ''))}")
        return NodeStatus.SUCCESS


def build_package_tree() -> SequenceNode:
    """Constructs Stage 6 PackageRoot Behavior Tree."""
    return SequenceNode("PackageRoot", [
        DAWSessionGenerateNode(),
        LiveDashboardExportNode(),
        ZIPArchivePackagerNode(),
    ])
