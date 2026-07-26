import os
import shutil
import tempfile
import pytest
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.stem_separation_bt import StrictStemDirectoryGuardNode, build_stem_separation_tree


class TestSDDPass22StemGuard:
    @pytest.fixture
    def mock_stems_dir(self):
        tmpdir = tempfile.mkdtemp()
        stems_dir = os.path.join(tmpdir, "stems")
        os.makedirs(stems_dir, exist_ok=True)

        # 模擬根目錄合法與非法檔案
        with open(os.path.join(stems_dir, "no_vocals.wav"), "w") as f: f.write("fake")
        with open(os.path.join(stems_dir, "instrumental.wav"), "w") as f: f.write("fake")
        with open(os.path.join(stems_dir, "guitar.wav"), "w") as f: f.write("fake")
        with open(os.path.join(stems_dir, "no_guitar.wav"), "w") as f: f.write("fake")
        with open(os.path.join(stems_dir, "residual_tier1.wav"), "w") as f: f.write("fake")

        # 模擬 vocals 子目錄混入雜檔
        vocal_dir = os.path.join(stems_dir, "vocals")
        os.makedirs(vocal_dir, exist_ok=True)
        with open(os.path.join(vocal_dir, "vocals.wav"), "w") as f: f.write("fake")
        with open(os.path.join(vocal_dir, "lead_vocal.wav"), "w") as f: f.write("fake")
        with open(os.path.join(vocal_dir, "bass.wav"), "w") as f: f.write("fake")
        with open(os.path.join(vocal_dir, "drums.wav"), "w") as f: f.write("fake")

        yield stems_dir

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_strict_stem_directory_guard(self, mock_stems_dir):
        bb = Blackboard()
        bb.set_val("stems_dir", mock_stems_dir)

        guard_node = StrictStemDirectoryGuardNode()
        status = guard_node.execute(bb)

        assert status == NodeStatus.SUCCESS

        # 1. 驗證根目錄只留 no_vocals.wav 與 instrumental.wav
        root_files = os.listdir(mock_stems_dir)
        assert "no_vocals.wav" in root_files
        assert "instrumental.wav" in root_files
        assert "guitar.wav" not in root_files  # 應被搬移至 guitars/
        assert "no_guitar.wav" not in root_files  # 應被刪除
        assert "residual_tier1.wav" not in root_files  # 應被刪除

        # 2. 驗證 guitar.wav 搬移至 guitars/
        guitar_dir = os.path.join(mock_stems_dir, "guitars")
        assert os.path.exists(os.path.join(guitar_dir, "guitar.wav"))

        # 3. 驗證 vocals 子目錄中的異物 (bass.wav, drums.wav) 被清理刪除
        vocal_dir = os.path.join(mock_stems_dir, "vocals")
        vocal_files = os.listdir(vocal_dir)
        assert "vocals.wav" in vocal_files
        assert "lead_vocal.wav" in vocal_files
        assert "bass.wav" not in vocal_files
        assert "drums.wav" not in vocal_files
