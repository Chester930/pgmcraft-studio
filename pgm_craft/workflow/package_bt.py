"""
Stage 6: Package & DAW Material Handoff Behavior Tree (PackageRoot)
"""

import os
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode
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


class DAWPresetsPackagerNode(BaseNode):
    """
    【全 DAW 專案檔一鍵預設包導出節點】
    - 彙整 Ableton Live (.als)、REAPER (.rpp)、Cubase (.csv) 與 MIDI 素材
    - 打包產生獨立檔 daw_presets_pack.zip 供全平台 DAW 使用
    """
    required_keys = ["output_dir"]
    output_keys = ["daw_presets_pack_path"]

    def __init__(self):
        super().__init__("DAWPresetsPackagerNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import zipfile
        output_dir = blackboard.get_val("output_dir", "outputs")
        zip_path = os.path.join(output_dir, "daw_presets_pack.zip")

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        if file.endswith(('.als', '.rpp', '.csv', '.mid', '.txt', '.md')) and file != "daw_presets_pack.zip":
                            fp = os.path.join(root, file)
                            arcname = os.path.relpath(fp, output_dir).replace("\\", "/")
                            zinfo = zipfile.ZipInfo.from_file(fp, arcname)
                            zinfo.flag_bits |= 0x800  # Pass 167: UTF-8 Filename Encoding Flag
                            with open(fp, "rb") as f_in:
                                zipf.writestr(zinfo, f_in.read())

            blackboard.set_val("daw_presets_pack_path", zip_path)
            outputs = blackboard.get_val("outputs", {})
            outputs["daw_presets_pack"] = zip_path
            blackboard.set_val("outputs", outputs)
            print(f"[{self.name}] 📦 成功打包全 DAW 一鍵預設工程包 ➔ {zip_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 打包 DAW 預設包失敗: {e}")
            return NodeStatus.SUCCESS


def build_package_tree() -> SequenceNode:
    """Constructs Stage 6 PackageRoot Behavior Tree."""
    return SequenceNode("PackageRoot", [
        DAWSessionGenerateNode(),
        LiveDashboardExportNode(),
        ZIPArchivePackagerNode(),
        DAWPresetsPackagerNode()
    ])
