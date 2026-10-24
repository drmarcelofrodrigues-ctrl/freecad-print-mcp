"""awcad — helpers de modelagem para impressão 3D, para rodar DENTRO do FreeCAD.

Este módulo é importado automaticamente pelos scripts que o servidor MCP envia ao
FreeCADCmd. Ele embrulha a API `Part` do FreeCAD com funções pensadas para peças
funcionais impressas em FDM (Bambu Lab A1 e similares): cavidades de ímã, furos
com folga, chanfro de base contra "pé de elefante", juntas esféricas, matrizes,
exportação em STL/3MF/STEP e medições.

Convenções
----------
* Unidades em milímetros. Z é "para cima" = direção de impressão.
* Funções recebem e devolvem `Part.Shape`; nada é adicionado ao documento até
  `export()` ou `show()`.
* Peças devem ter a base em Z = 0 (use `on_bed()`).
* Tudo que for exportado/medido vai para `RESULT`, que volta ao Claude como JSON.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import FreeCAD as App  # type: ignore
import Part  # type: ignore

V = App.Vector
X, Y, Z = V(1, 0, 0), V(0, 1, 0), V(0, 0, 1)

# Estado preenchido pelo bootstrap do servidor
RESULT: dict = {"exports": [], "measures": {}, "notes": []}
DOC = None
_OUTPUT_DIR = Path(os.getcwd())
_NAME = "modelo"
_SHOWN: list = []

# ---------------------------------------------------------------------------
# Tolerâncias padrão para PLA no A1 (ajuste após calibrar com examples/teste_folgas.py)
# ---------------------------------------------------------------------------
TOL = {
    "magnet": 0.15,       # folga radial para ímã de neodímio entrar à mão e ficar firme
    "press_fit": 0.05,    # encaixe por pressão (apertado)
    "slide_fit": 0.20,    # encaixe deslizante (entra/sai)
    "loose_fit": 0.40,    # encaixe folgado (peça gira livre)
    "hole_shrink": 0.20,  # furos saem ~0,2 mm menores em FDM: some isto ao diâmetro
    "min_wall": 1.2,      # 3 perímetros de 0,4 mm
    "elephant_foot": 0.4, # chanfro na base para compensar a 1ª camada esmagada
}

# Parafusos métricos: (furo passante com folga, furo para rosquear direto no plástico, diâmetro cabeça, altura cabeça)
SCREWS = {
    "M2":   {"through": 2.4, "tap": 1.8, "head_d": 3.8, "head_h": 2.0},
    "M2.5": {"through": 2.9, "tap": 2.2, "head_d": 4.5, "head_h": 2.5},
    "M3":   {"through": 3.4, "tap": 2.6, "head_d": 5.7, "head_h": 3.0},
    "M4":   {"through": 4.5, "tap": 3.4, "head_d": 7.2, "head_h": 4.0},
    "M5":   {"through": 5.5, "tap": 4.3, "head_d": 8.7, "head_h": 5.0},
}


def configure(output_dir: str, name: str) -> None:
    global _OUTPUT_DIR, _NAME
    _OUTPUT_DIR = Path(output_dir)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _NAME = name


def note(msg: str) -> None:
    """Anota uma observação que volta ao Claude no RESULT."""
    RESULT["notes"].append(str(msg))


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
def box(l: float, w: float, h: float, center: bool = False) -> Part.Shape:
    """Caixa l×w×h. Com center=True fica centrada em XY, base em Z=0."""
    s = Part.makeBox(l, w, h)
    if center:
        s.translate(V(-l / 2, -w / 2, 0))
    return s


def cyl(d: float, h: float, center: bool = True) -> Part.Shape:
    """Cilindro de diâmetro d e altura h, eixo Z, base em Z=0. center=True → eixo na origem."""
    s = Part.makeCylinder(d / 2, h)
    if not center:
        s.translate(V(d / 2, d / 2, 0))
    return s


def sphere(d: float, at=(0, 0, 0)) -> Part.Shape:
    return Part.makeSphere(d / 2, V(*at))


def cone(d1: float, d2: float, h: float) -> Part.Shape:
    return Part.makeCone(d1 / 2, d2 / 2, h)


def rounded_box(l: float, w: float, h: float, r: float, center: bool = False) -> Part.Shape:
    """Caixa com cantos verticais arredondados (raio r). Ótima como base de suportes."""
    s = box(l, w, h, center)
    edges = [e for e in s.Edges if _is_vertical(e)]
    return s.makeFillet(r, edges)


def wedge(l: float, w: float, h_front: float, h_back: float) -> Part.Shape:
    """Cunha/rampa: comprimento l (X), largura w (Y), altura h_front em X=0 e h_back em X=l."""
    pts = [V(0, 0, 0), V(l, 0, 0), V(l, 0, h_back), V(0, 0, h_front), V(0, 0, 0)]
    face = Part.Face(Part.makePolygon(pts))
    return face.extrude(V(0, w, 0))


def polygon_prism(points: list, h: float) -> Part.Shape:
    """Prisma a partir de um polígono 2D [(x,y), ...] extrudado em Z."""
    pts = [V(x, y, 0) for x, y in points]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, h))


# ---------------------------------------------------------------------------
# Transformações e booleanas (devolvem cópias)
# ---------------------------------------------------------------------------
def move(s: Part.Shape, x=0.0, y=0.0, z=0.0) -> Part.Shape:
    c = s.copy()
    c.translate(V(x, y, z))
    return c


def rotate(s: Part.Shape, angle: float, axis=Z, center=(0, 0, 0)) -> Part.Shape:
    c = s.copy()
    c.rotate(V(*center), axis, angle)
    return c


def mirror_x(s: Part.Shape) -> Part.Shape:
    return s.mirror(V(0, 0, 0), X)


def fuse(*shapes: Part.Shape) -> Part.Shape:
    base = shapes[0]
    for s in shapes[1:]:
        base = base.fuse(s)
    return base.removeSplitter()


def cut(base: Part.Shape, *tools: Part.Shape) -> Part.Shape:
    for t in tools:
        base = base.cut(t)
    return base.removeSplitter()


def common(a: Part.Shape, b: Part.Shape) -> Part.Shape:
    return a.common(b)


def on_bed(s: Part.Shape) -> Part.Shape:
    """Desloca a peça para que a face inferior fique em Z = 0."""
    return move(s, z=-s.BoundBox.ZMin)


def center_xy(s: Part.Shape) -> Part.Shape:
    bb = s.BoundBox
    return move(s, x=-(bb.XMin + bb.XLength / 2), y=-(bb.YMin + bb.YLength / 2))


def array(s: Part.Shape, n: int, pitch: float, axis=X) -> Part.Shape:
    """n cópias fundidas, espaçadas por pitch ao longo do eixo."""
    ax = _vec(axis)
    parts = []
    for i in range(n):
        off = ax * (i * pitch)
        parts.append(move(s, off.x, off.y, off.z))
    return fuse(*parts)


def grid(s: Part.Shape, nx: int, ny: int, px: float, py: float) -> Part.Shape:
    return array(array(s, nx, px, X), ny, py, Y)


# ---------------------------------------------------------------------------
# Recursos para impressão 3D
# ---------------------------------------------------------------------------
def magnet_cavity(
    base: Part.Shape,
    at,
    d: float = 5.0,
    h: float = 2.0,
    clearance: float | None = None,
    depth_extra: float = 0.2,
    axis=Z,
    through: bool = False,
) -> Part.Shape:
    """Corta uma cavidade cilíndrica para ímã (padrão 5×2 mm).

    at: ponto (x, y, z) do CENTRO DA BOCA da cavidade (face por onde o ímã entra).
    axis: direção apontando para DENTRO da peça a partir da boca.
    clearance: folga radial (padrão TOL['magnet']). depth_extra deixa o ímã 0,2 mm rebaixado.
    """
    c = TOL["magnet"] if clearance is None else clearance
    depth = (h + depth_extra) if not through else 1000
    ax = _vec(axis)
    # começa 0,01 fora para garantir corte limpo na face
    tool = Part.makeCylinder(d / 2 + c, depth + 0.01, V(*at) - ax * 0.01, ax)
    return cut(base, tool)


def hole(base: Part.Shape, at, d: float, depth: float | None = None, axis=Z, fdm_compensate: bool = True) -> Part.Shape:
    """Furo cilíndrico. at = centro na face de entrada; axis aponta para dentro.
    fdm_compensate soma TOL['hole_shrink'] ao diâmetro (furos saem menores em FDM)."""
    dd = d + (TOL["hole_shrink"] if fdm_compensate else 0)
    ax = _vec(axis)
    dep = depth if depth is not None else 1000
    tool = Part.makeCylinder(dd / 2, dep + 0.02, V(*at) - ax * 0.01, ax)
    return cut(base, tool)


def screw_hole(base: Part.Shape, at, size: str = "M3", kind: str = "through", depth: float | None = None, countersink: bool = False) -> Part.Shape:
    """Furo para parafuso métrico. kind: 'through' (passante com folga) ou 'tap' (rosquear no plástico).
    countersink=True adiciona rebaixo para a cabeça (cabeça fica faceada), entrando por cima (-Z)."""
    sp = SCREWS[size]
    dia = sp[kind]
    s = hole(base, at, dia, depth, axis=-Z if countersink else Z, fdm_compensate=(kind == "through"))
    if countersink:
        x, y, z = at
        head = Part.makeCylinder(sp["head_d"] / 2 + 0.2, sp["head_h"] + 0.01, V(x, y, z - sp["head_h"]), Z)
        s = cut(s, head)
    return s


def chamfer_bottom(s: Part.Shape, size: float | None = None) -> Part.Shape:
    """Chanfra todas as arestas da face inferior (anti pé de elefante)."""
    sz = TOL["elephant_foot"] if size is None else size
    zmin = s.BoundBox.ZMin
    edges = [e for e in s.Edges if e.BoundBox.ZMax - zmin < 1e-3 and e.BoundBox.ZMin - zmin > -1e-3]
    if not edges:
        return s
    try:
        return s.makeChamfer(sz, edges)
    except Exception as ex:  # noqa: BLE001
        note(f"chamfer_bottom falhou ({ex}); peça devolvida sem chanfro")
        return s


def fillet_vertical(s: Part.Shape, r: float) -> Part.Shape:
    """Arredonda todas as arestas verticais (cantos vistos de cima)."""
    edges = [e for e in s.Edges if _is_vertical(e)]
    return s.makeFillet(r, edges) if edges else s


def fillet_top(s: Part.Shape, r: float) -> Part.Shape:
    zmax = s.BoundBox.ZMax
    edges = [e for e in s.Edges if abs(e.BoundBox.ZMin - zmax) < 1e-3 and abs(e.BoundBox.ZMax - zmax) < 1e-3]
    return s.makeFillet(r, edges) if edges else s


def fillet_all(s: Part.Shape, r: float) -> Part.Shape:
    try:
        return s.makeFillet(r, s.Edges)
    except Exception as ex:  # noqa: BLE001
        note(f"fillet_all falhou ({ex}); tente raio menor ou fillet_vertical")
        return s


def shell(s: Part.Shape, wall: float, open_top: bool = True) -> Part.Shape:
    """Transforma um sólido em casca com espessura wall. open_top remove a face superior (vira uma caixa aberta)."""
    faces = []
    if open_top:
        zmax = s.BoundBox.ZMax
        faces = [f for f in s.Faces if abs(f.BoundBox.ZMin - zmax) < 1e-3 and abs(f.BoundBox.ZMax - zmax) < 1e-3]
    return s.makeThickness(faces, -abs(wall), 1e-3)


def channel_round(base: Part.Shape, d: float, length: float, at, axis=X, open_ratio: float = 1.0) -> Part.Shape:
    """Canaleta semicircular (berço) para tubo/seringa de diâmetro d, cortada a partir do topo.
    at = ponto inicial do eixo do cilindro (centro da seção). open_ratio>1 alarga a boca."""
    ax = _vec(axis)
    x, y, z = at
    # ferramenta montada na origem ao longo de X: cilindro + bloco que abre o berço até o topo
    c = Part.makeCylinder(d / 2, length, V(0, 0, 0), X)
    top_h = base.BoundBox.ZMax - z + 1
    top = Part.makeBox(length, d * open_ratio, max(top_h, 0.1))
    top.translate(V(0, -d * open_ratio / 2, 0))
    tool = c.fuse(top)
    if ax.isEqual(Y, 1e-6):
        tool.rotate(V(0, 0, 0), Z, 90)
    tool.translate(V(x, y, z))
    return cut(base, tool)


def ball_socket(
    d_ball: float,
    clearance: float = -0.05,
    wall: float = 2.5,
    opening_ratio: float = 0.88,
    slots: int = 4,
    slot_width: float = 1.0,
    slot_depth_ratio: float = 0.7,
) -> Part.Shape:
    """Soquete para junta esférica, pensado para segurar pose em PLA.

    Lições dos testes no A1: folga positiva (0,15–0,2) entra fácil mas não trava;
    para articulação com atrito use folga ZERO ou NEGATIVA (interferência de ~0,05) com
    fendas (slots) que deixam as paredes flexionarem. Esfera impressa com `ball()`.

    Retorna um cilindro com a cavidade esférica aberta para +Z (boca em cima).
    opening_ratio: diâmetro da boca / diâmetro da esfera (0,85–0,92 trava bem).
    """
    r_cav = d_ball / 2 + clearance
    outer_d = d_ball + 2 * wall
    # a boca (no topo, z=h) deve ter raio r_cav*opening_ratio → fica dz acima do centro da esfera
    dz = r_cav * math.sqrt(max(0.0, 1 - opening_ratio ** 2))
    h = wall + r_cav + dz  # fundo + raio + subida até a boca
    center_z = wall + r_cav
    body = cyl(outer_d, h)
    cav = sphere(2 * r_cav, (0, 0, center_z))
    body = cut(body, cav)
    # abertura cilíndrica da boca para cima
    mouth = Part.makeCylinder(r_cav * opening_ratio, h, V(0, 0, center_z), Z)
    body = cut(body, mouth)
    # fendas
    if slots > 0:
        slot_h = h * slot_depth_ratio
        for i in range(slots):
            sl = Part.makeBox(outer_d + 2, slot_width, slot_h)
            sl.translate(V(-outer_d / 2 - 1, -slot_width / 2, h - slot_h))
            sl.rotate(V(0, 0, 0), Z, i * 180.0 / slots)
            body = body.cut(sl)
    return body.removeSplitter()


def ball(d: float, stem_d: float | None = None, stem_h: float = 4.0) -> Part.Shape:
    """Esfera para junta, com haste opcional por baixo (para fundir em outra peça)."""
    s = sphere(d, (0, 0, d / 2 + stem_h))
    if stem_d:
        s = fuse(s, cyl(stem_d, stem_h + d / 4))
    return s


def text_label(base: Part.Shape, text: str, size: float = 6.0, at=(0, 0, 0), depth: float = 0.6, font: str | None = None, emboss: bool = False) -> Part.Shape:
    """Grava (ou eleva) texto na face superior em Z=at[2]. Precisa de uma fonte TTF.
    No Windows: C:/Windows/Fonts/arial.ttf. Linux: /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"""
    f = font or _default_font()
    if not f:
        note("text_label: fonte não encontrada; passe font='caminho.ttf'")
        return base
    wires = Part.makeWireString(text, f, size, 0)
    faces = []
    for group in wires:  # um grupo por caractere; espaços vêm vazios
        if not group:
            continue
        # contorno externo = maior área; os demais são furos (ex.: "0", "8", "A")
        char_faces = sorted((Part.Face(w) for w in group), key=lambda fc: fc.Area, reverse=True)
        face = char_faces[0]
        for inner in char_faces[1:]:
            face = face.cut(inner)
        faces.append(face)
    if not faces:
        return base
    solid = None
    for face in faces:
        ext = face.extrude(V(0, 0, depth if emboss else -depth))
        solid = ext if solid is None else solid.fuse(ext)
    solid.translate(V(*at))
    return fuse(base, solid) if emboss else cut(base, solid)


# ---------------------------------------------------------------------------
# Medição, documento e exportação
# ---------------------------------------------------------------------------
def bbox(s: Part.Shape):
    """Caixa envolvente justa (BoundBox padrão é folgado em superfícies curvas)."""
    try:
        return s.optimalBoundingBox(True)
    except Exception:  # noqa: BLE001
        return s.BoundBox


def measure(s: Part.Shape, label: str = "shape") -> dict:
    bb = bbox(s)
    vol_mm3 = s.Volume
    m = {
        "bbox_mm": [round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)],
        "bbox_min": [round(bb.XMin, 2), round(bb.YMin, 2), round(bb.ZMin, 2)],
        "volume_cm3": round(vol_mm3 / 1000, 2),
        "area_cm2": round(s.Area / 100, 1),
        "mass_pla_g_solid": round(vol_mm3 / 1000 * 1.24, 1),
        "solids": len(s.Solids),
        "valid": bool(s.isValid()),
    }
    try:
        cm = s.Solids[0].CenterOfMass if len(s.Solids) == 1 else s.CenterOfMass
        m["center_of_mass"] = [round(cm.x, 2), round(cm.y, 2), round(cm.z, 2)]
    except Exception:  # noqa: BLE001
        pass
    if abs(bb.ZMin) > 1e-3:
        m["warning"] = f"base não está em Z=0 (ZMin={bb.ZMin:.2f}); use on_bed()"
    RESULT["measures"][label] = m
    return m


def show(s: Part.Shape, label: str = "Peca") -> object:
    """Adiciona a shape ao documento (útil para salvar .FCStd)."""
    obj = DOC.addObject("Part::Feature", label)
    obj.Shape = s
    _SHOWN.append(obj)
    return obj


def export(
    s: Part.Shape,
    name: str | None = None,
    formats=("stl", "3mf"),
    linear_deflection: float = 0.02,
    angular_deflection_deg: float = 10.0,
    save_fcstd: bool = False,
) -> list:
    """Exporta a shape. Mede, valida e grava STL/3MF/STEP em OUTPUT_DIR. Retorna caminhos.

    linear_deflection 0,02 mm = malha fina (bom para peças pequenas e superfícies curvas).
    """
    import Mesh  # type: ignore
    import MeshPart  # type: ignore

    nm = _slug(name or _NAME)
    if not s.isValid():
        note(f"{nm}: shape inválida segundo isValid(); tentando exportar mesmo assim")
    if len(s.Solids) > 1:
        note(f"{nm}: {len(s.Solids)} sólidos separados — vão como um único arquivo; confira se é intencional")
    measure(s, nm)

    obj = show(s, nm)
    paths = []
    needs_mesh = any(f in ("stl", "3mf", "obj") for f in formats)
    if needs_mesh:
        mesh = MeshPart.meshFromShape(
            Shape=s,
            LinearDeflection=linear_deflection,
            AngularDeflection=math.radians(angular_deflection_deg),
            Relative=False,
        )
        mobj = DOC.addObject("Mesh::Feature", nm + "_mesh")
        mobj.Mesh = mesh
        for fmt in formats:
            if fmt in ("stl", "3mf", "obj"):
                p = _OUTPUT_DIR / f"{nm}.{fmt}"
                Mesh.export([mobj], str(p))
                paths.append(str(p))
        RESULT["measures"][nm]["mesh_faces"] = mesh.CountFacets
    if "step" in formats or "stp" in formats:
        import Import  # type: ignore
        p = _OUTPUT_DIR / f"{nm}.step"
        Import.export([obj], str(p))
        paths.append(str(p))
    if save_fcstd:
        p = _OUTPUT_DIR / f"{nm}.FCStd"
        DOC.saveAs(str(p))
        paths.append(str(p))

    RESULT["exports"].extend(paths)
    return paths


def _finish() -> None:
    """Chamado pelo epílogo: se o usuário não exportou nada mas deixou `part` definido, avisa."""
    if not RESULT["exports"] and not RESULT["measures"]:
        note("Nada foi exportado nem medido. Use awcad.export(shape, 'nome') ao final do script.")


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------
def _vec(a) -> App.Vector:
    """Aceita App.Vector, tupla ou lista; devolve vetor normalizado."""
    v = a if isinstance(a, App.Vector) else V(*a)
    return App.Vector(v).normalize()


def _is_vertical(e) -> bool:
    bb = e.BoundBox
    return bb.XLength < 1e-6 and bb.YLength < 1e-6 and bb.ZLength > 1e-6


def _slug(s: str) -> str:
    keep = [c if c.isalnum() or c in "-_" else "-" for c in s.strip()]
    return "".join(keep).strip("-")[:60] or "modelo"


def _default_font() -> str | None:
    for p in (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if os.path.exists(p):
            return p
    return None
