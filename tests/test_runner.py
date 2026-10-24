import os
import shutil
from pathlib import Path

import pytest

from freecad_print_mcp import runner, server


def test_build_script_wraps_user_code(tmp_path):
    s = runner.build_script("x = awcad.box(1, 2, 3)\nawcad.export(x, 'x')", tmp_path, "teste")
    assert "import awcad" in s
    assert "    x = awcad.box(1, 2, 3)" in s  # indentado dentro do try
    assert runner.RESULT_MARKER in s


def test_clean_stdout_removes_banner_and_progress():
    raw = "FreeCAD 1.0.2, Libs: 1.0.2R39319 (Git)\n(C) 2001-2025 FreeCAD contributors\nsaving......\n\t\t(42 %)\t\nexportado: ok\n"
    assert runner.clean_stdout(raw) == "exportado: ok"


def test_awcad_reference_lists_functions():
    ref = server.awcad_reference()
    for fn in ("magnet_cavity", "chamfer_bottom", "ball_socket", "export"):
        assert f"awcad.{fn}(" in ref
    assert "awcad.ball_socket(" in server.awcad_reference("ball_socket")


@pytest.mark.skipif(runner.find_freecadcmd() is None, reason="FreeCAD não instalado")
def test_selftest_with_real_freecad(tmp_path, monkeypatch):
    monkeypatch.setenv("FCMCP_OUTPUT_DIR", str(tmp_path))
    rr = runner.run_script("awcad.export(awcad.chamfer_bottom(awcad.box(10, 10, 5)), 'cubo')", name="t")
    assert rr.ok, rr.stderr
    assert any(p.endswith("cubo.stl") for p in rr.result["exports"])
    assert rr.result["measures"]["cubo"]["bbox_mm"] == [10.0, 10.0, 5.0]
