import trimesh

from freecad_print_mcp import mesh_tools


def _t_shape(tmp_path):
    base = trimesh.creation.box((10, 10, 30))
    base.apply_translation((0, 0, 15))
    top = trimesh.creation.box((40, 10, 5))
    top.apply_translation((0, 0, 32.5))
    m = trimesh.util.concatenate([base, top])
    p = tmp_path / "t.stl"
    m.export(p)
    return p


def test_measure(tmp_path):
    r = mesh_tools.measure(_t_shape(tmp_path))
    assert r["bbox_mm"] == [40.0, 10.0, 35.0]
    assert r["watertight"] is True
    assert abs(r["volume_cm3"] - 5.0) < 0.01


def test_printability_prefers_lying_down(tmp_path):
    r = mesh_tools.check_printability(_t_shape(tmp_path))
    assert r["orientation_as_is"]["overhang_pct"] > 10
    best = r["orientation_ranking"][0]
    assert best["overhang_pct"] == 0.0
    assert best["orientation"].startswith("deitada_x")


def test_render_png(tmp_path):
    png = mesh_tools.render_png(_t_shape(tmp_path), views="iso,top")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 5000
