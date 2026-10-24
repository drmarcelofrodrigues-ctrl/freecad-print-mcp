"""Análise de malhas (STL/3MF/OBJ) para impressão FDM, sem depender do FreeCAD.

Usa trimesh + numpy. Serve para medir, checar imprimibilidade e gerar um PNG de
preview que o Claude consegue "ver" no chat.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
import trimesh

PLA_DENSITY_G_CM3 = 1.24


def load_mesh(path: str | Path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate(tuple(g for g in m.geometry.values()))
    return m


def measure(path: str | Path) -> dict:
    m = load_mesh(path)
    ext = m.bounding_box.extents
    vol = float(m.volume) if m.is_volume else None
    out = {
        "file": str(path),
        "bbox_mm": [round(float(x), 2) for x in ext],
        "faces": int(len(m.faces)),
        "vertices": int(len(m.vertices)),
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "bodies": int(len(m.split(only_watertight=False))),
        "area_cm2": round(float(m.area) / 100, 1),
    }
    if vol is not None:
        out["volume_cm3"] = round(vol / 1000, 2)
        out["mass_pla_g_solid"] = round(vol / 1000 * PLA_DENSITY_G_CM3, 1)
        out["mass_pla_g_15pct_infill_est"] = round(_estimate_mass_g(m, vol), 1)
    else:
        out["volume_cm3"] = None
        out["warning"] = "Malha não é um volume fechado; volume/massa indisponíveis"
    return out


def _estimate_mass_g(m: trimesh.Trimesh, vol_mm3: float, wall_mm: float = 1.2, infill: float = 0.15) -> float:
    """Estimativa grosseira: cascas sólidas de `wall_mm` + miolo com `infill`."""
    shell = min(vol_mm3, float(m.area) * wall_mm)
    core = max(vol_mm3 - shell, 0.0) * infill
    return (shell + core) / 1000 * PLA_DENSITY_G_CM3


ORIENTATIONS = {
    "como_esta": np.eye(4),
    "virada_180_x": trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]),
    "deitada_x_90": trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]),
    "deitada_x_-90": trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]),
    "deitada_y_90": trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]),
    "deitada_y_-90": trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0]),
}


def _overhang_stats(m: trimesh.Trimesh, max_overhang_deg: float) -> dict:
    """Área de faces que precisam de suporte e área de contato com a mesa."""
    normals = m.face_normals
    areas = m.area_faces
    zmin = m.bounds[0][2]
    # faces encostadas na mesa (dentro de 0,05 mm) não contam como balanço
    face_z = m.triangles[:, :, 2]
    on_bed = np.all(face_z - zmin < 0.05, axis=1)
    # ângulo entre a normal e "para baixo" (-Z)
    cos_down = -normals[:, 2]
    limit = math.cos(math.radians(max_overhang_deg))  # 45° → faces com normal a <45° de -Z
    overhang = (cos_down > limit) & (~on_bed)
    total = float(areas.sum())
    return {
        "overhang_area_mm2": float(areas[overhang].sum()),
        "overhang_pct": round(100 * float(areas[overhang].sum()) / total, 1) if total else 0.0,
        "bed_contact_mm2": float(areas[on_bed].sum()),
        "height_mm": float(m.bounds[1][2] - zmin),
    }


def check_printability(
    path: str | Path,
    nozzle_mm: float = 0.4,
    layer_mm: float = 0.2,
    max_overhang_deg: float = 45.0,
    bed_mm: tuple = (256, 256, 256),
    try_orientations: bool = True,
) -> dict:
    m = load_mesh(path)
    issues: list[str] = []
    tips: list[str] = []

    ext = m.bounding_box.extents
    if any(e > b for e, b in zip(ext, bed_mm)):
        issues.append(f"Peça ({[round(float(e),1) for e in ext]} mm) excede o volume da mesa {bed_mm}")

    if not m.is_watertight:
        issues.append("Malha não é fechada (watertight=False): o fatiador pode gerar camadas erradas. Use Mesh → Analisar → Avaliar e reparar no FreeCAD, ou removeSplitter() antes de exportar")
    if not m.is_winding_consistent:
        issues.append("Normais inconsistentes (faces viradas)")
    bodies = m.split(only_watertight=False)
    if len(bodies) > 1:
        tiny = [b for b in bodies if b.bounding_box.extents.max() < nozzle_mm * 2]
        issues.append(f"{len(bodies)} corpos separados no mesmo arquivo" + (f"; {len(tiny)} são fragmentos minúsculos (<{nozzle_mm*2} mm)" if tiny else ""))

    min_dim = float(ext.min())
    if min_dim < layer_mm * 2:
        issues.append(f"Dimensão mínima {min_dim:.2f} mm é menor que 2 camadas ({layer_mm*2} mm)")

    base = _overhang_stats(m, max_overhang_deg)
    result: dict = {
        "file": str(path),
        "bbox_mm": [round(float(x), 2) for x in ext],
        "watertight": bool(m.is_watertight),
        "orientation_as_is": {k: round(v, 1) for k, v in base.items()},
    }

    if base["overhang_pct"] > 0.5:
        tips.append(f"{base['overhang_pct']}% da área está em balanço >{max_overhang_deg}°: precisa de suporte ou outra orientação")
    if base["bed_contact_mm2"] < 25 and base["height_mm"] > 20:
        tips.append("Pouco contato com a mesa para a altura: risco de descolar/tombar; considere aba (brim) ou deitar a peça")
    aspect = base["height_mm"] / max(math.sqrt(base["bed_contact_mm2"]), 1e-6)
    if aspect > 6:
        tips.append(f"Peça alta e fina (razão {aspect:.1f}): oscilação no topo; reduza velocidade ou imprima deitada")

    if try_orientations:
        ranking = []
        for name, T in ORIENTATIONS.items():
            mm = m.copy()
            mm.apply_transform(T)
            st = _overhang_stats(mm, max_overhang_deg)
            ranking.append({
                "orientation": name,
                "overhang_pct": st["overhang_pct"],
                "bed_contact_mm2": round(st["bed_contact_mm2"], 1),
                "height_mm": round(st["height_mm"], 1),
            })
        ranking.sort(key=lambda r: (r["overhang_pct"], -r["bed_contact_mm2"], r["height_mm"]))
        result["orientation_ranking"] = ranking
        best = ranking[0]
        if best["orientation"] != "como_esta" and best["overhang_pct"] + 1.0 < base["overhang_pct"]:
            tips.append(f"Orientação '{best['orientation']}' reduz balanço de {base['overhang_pct']}% para {best['overhang_pct']}%")

    result["issues"] = issues
    result["tips"] = tips
    result["verdict"] = "OK" if not issues else ("ATENÇÃO" if m.is_watertight else "CORRIGIR")
    return result


def render_png(path: str | Path, views: str = "iso,top,front,right", size_px: int = 900, color: str = "#4F8EF7") -> bytes:
    """Renderiza a malha em PNG (matplotlib, sem OpenGL). Retorna bytes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    m = load_mesh(path)
    if len(m.faces) > 120_000:
        # amostra para não travar o render; visual aproximado
        idx = np.random.default_rng(0).choice(len(m.faces), 120_000, replace=False)
        tris = m.triangles[idx]
        normals = m.face_normals[idx]
    else:
        tris = m.triangles
        normals = m.face_normals

    view_list = [v.strip() for v in views.split(",") if v.strip()]
    angles = {"iso": (30, -60), "top": (90, -90), "front": (0, -90), "right": (0, 0), "back": (0, 90), "left": (0, 180), "bottom": (-90, -90)}
    n = len(view_list)
    cols = 2 if n > 1 else 1
    rows = math.ceil(n / cols)
    dpi = 100
    fig = plt.figure(figsize=(size_px / dpi, size_px / dpi * rows / cols), dpi=dpi)

    # sombreamento simples por direção de luz
    light = np.array([0.4, -0.6, 0.7])
    light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(normals @ light, 0, 1)
    base_rgb = np.array(matplotlib.colors.to_rgb(color))
    face_colors = np.clip(base_rgb[None, :] * shade[:, None], 0, 1)

    lo, hi = m.bounds
    center = (lo + hi) / 2
    radius = float(np.max(hi - lo)) / 2 * 1.05

    for i, v in enumerate(view_list):
        ax = fig.add_subplot(rows, cols, i + 1, projection="3d")
        elev, azim = angles.get(v, angles["iso"])
        # ordena as faces da mais distante para a mais próxima da câmera (painter's algorithm)
        e, a = math.radians(elev), math.radians(azim)
        cam = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        depth = tris.mean(axis=1) @ cam
        order = np.argsort(depth)
        coll = Poly3DCollection(tris[order], facecolors=face_colors[order], edgecolors="none")
        ax.add_collection3d(coll)
        ax.view_init(elev=elev, azim=azim)
        for setter, c in ((ax.set_xlim, center[0]), (ax.set_ylim, center[1]), (ax.set_zlim, center[2])):
            setter(c - radius, c + radius)
        ax.set_box_aspect((1, 1, 1))
        ax.set_title(f"{v}  ({hi[0]-lo[0]:.1f} × {hi[1]-lo[1]:.1f} × {hi[2]-lo[2]:.1f} mm)", fontsize=9)
        ax.set_axis_off()

    fig.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    plt.close(fig)
    return buf.getvalue()
