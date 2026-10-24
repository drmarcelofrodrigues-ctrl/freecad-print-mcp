"""Servidor MCP: FreeCAD headless + análise de malha para impressão 3D.

Executar:  freecad-print-mcp   (ou  python -m freecad_print_mcp.server)
Transporte: stdio (padrão para Claude Desktop / Claude Code).
"""

from __future__ import annotations

import ast
import json
import os
import platform
import subprocess
from pathlib import Path

try:  # SDK mcp >= 2.0
    from mcp.server.mcpserver import Image, MCPServer as FastMCP
except ImportError:  # SDK mcp 1.x
    from mcp.server.fastmcp import FastMCP, Image

from . import mesh_tools, runner

mcp = FastMCP(
    "freecad-print",
    instructions=(
        "Ferramentas para modelar peças de impressão 3D no FreeCAD sem abrir a interface. "
        "Fluxo típico: 1) awcad_reference para ver os helpers; 2) freecad_run com um script Python "
        "usando `awcad` e terminando em awcad.export(shape, 'nome'); 3) mesh_render para ver o resultado; "
        "4) mesh_check_printability antes de mandar para o fatiador; 5) open_file para abrir o 3MF no Bambu Studio. "
        "Unidades em mm, Z para cima, base da peça em Z=0."
    ),
)


def _json(d) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# FreeCAD
# ---------------------------------------------------------------------------
@mcp.tool()
def freecad_status() -> str:
    """Verifica se o FreeCADCmd foi encontrado, sua versão e a pasta de saída configurada."""
    info = runner.freecad_version()
    info["output_dir"] = str(runner.default_output_dir())
    info["platform"] = platform.platform()
    return _json(info)


@mcp.tool()
def freecad_run(code: str, name: str = "modelo", timeout_s: int = 180) -> str:
    """Executa um script Python dentro do FreeCAD headless e devolve exportações + medidas.

    O script já tem disponíveis: `App` (FreeCAD), `Part`, `awcad` (helpers) e `doc` (documento vazio).
    Vetores: `awcad.V(x, y, z)` ou `App.Vector`; eixos `awcad.X/Y/Z`. Termine com
    `awcad.export(shape, "nome-da-peca")` para gerar STL+3MF na pasta de saída; use `awcad.measure(shape)`
    só para medir sem exportar. Prints aparecem no retorno. Peça sempre com a base em Z=0 (awcad.on_bed).

    Exemplo mínimo:
        s = awcad.rounded_box(40, 30, 10, r=3, center=True)
        s = awcad.magnet_cavity(s, at=(10, 0, 10), d=5, h=2, axis=-awcad.Z)
        s = awcad.chamfer_bottom(s)
        awcad.export(s, "base-ima")

    name: prefixo do arquivo de script salvo em <saida>/_scripts para rastreabilidade.
    """
    rr = runner.run_script(code, name=name, timeout=timeout_s)
    return _json(rr.summary() | {"script_saved_as": rr.script_path})


@mcp.tool()
def freecad_run_file(path: str, timeout_s: int = 180) -> str:
    """Executa um arquivo .py local (ex.: examples/suporte_seringas_20ml.py) no FreeCAD headless, com `awcad` disponível."""
    p = Path(path).expanduser()
    if not p.exists():
        return _json({"ok": False, "error": f"Arquivo não encontrado: {p}"})
    code = p.read_text(encoding="utf-8")
    rr = runner.run_script(code, name=p.stem, timeout=timeout_s)
    return _json(rr.summary())


@mcp.tool()
def freecad_selftest() -> str:
    """Roda um script curto que exercita os principais helpers do awcad. Use após instalar para confirmar que tudo funciona."""
    code = '''
s = awcad.rounded_box(30, 20, 8, r=2, center=True)
s = awcad.magnet_cavity(s, at=(8, 0, 8), d=5, h=2, axis=-awcad.Z)
s = awcad.screw_hole(s, at=(-8, 0, 8), size="M3", countersink=True)
s = awcad.chamfer_bottom(s)
j = awcad.ball_socket(11)
awcad.measure(j, "ball_socket_11mm")
paths = awcad.export(s, "selftest", formats=("stl", "3mf"))
print("exportado:", paths)
'''
    rr = runner.run_script(code, name="selftest")
    return _json(rr.summary())


@mcp.tool()
def awcad_reference(function: str = "") -> str:
    """Documentação dos helpers `awcad` (assinaturas + docstrings) disponíveis dentro de freecad_run.
    Passe `function` para ver só uma função; vazio lista todas."""
    src = (runner.LIB_DIR / "awcad.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            if function and node.name != function:
                continue
            sig = ast.unparse(node.args)
            doc = ast.get_docstring(node) or ""
            out.append(f"awcad.{node.name}({sig})\n    {doc}" if doc else f"awcad.{node.name}({sig})")
        elif isinstance(node, ast.Assign) and not function:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ("TOL", "SCREWS"):
                    out.append(f"awcad.{t.id} = {ast.unparse(node.value)}")
    header = ast.get_docstring(tree) or ""
    return (header + "\n\n" if not function else "") + "\n\n".join(out)


# ---------------------------------------------------------------------------
# Malhas
# ---------------------------------------------------------------------------
@mcp.tool()
def mesh_measure(path: str) -> str:
    """Mede um STL/3MF/OBJ: caixa envolvente, volume, massa estimada em PLA, faces, fechamento (watertight)."""
    return _json(mesh_tools.measure(_resolve(path)))


@mcp.tool()
def mesh_check_printability(
    path: str,
    nozzle_mm: float = 0.4,
    layer_mm: float = 0.2,
    max_overhang_deg: float = 45.0,
    bed_x_mm: float = 256,
    bed_y_mm: float = 256,
    bed_z_mm: float = 256,
) -> str:
    """Checa imprimibilidade FDM: malha fechada, corpos separados, dimensões mínimas, área em balanço,
    contato com a mesa e ranking de orientações. Padrão: Bambu Lab A1 (256³), bico 0,4, camada 0,2."""
    return _json(
        mesh_tools.check_printability(
            _resolve(path), nozzle_mm, layer_mm, max_overhang_deg, (bed_x_mm, bed_y_mm, bed_z_mm)
        )
    )


@mcp.tool()
def mesh_render(path: str, views: str = "iso,top,front,right", size_px: int = 900) -> Image:
    """Gera um PNG da malha para inspeção visual. views: lista separada por vírgula entre
    iso, top, bottom, front, back, left, right."""
    png = mesh_tools.render_png(_resolve(path), views=views, size_px=size_px)
    return Image(data=png, format="png")


# ---------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------
@mcp.tool()
def list_outputs(limit: int = 30) -> str:
    """Lista os arquivos mais recentes na pasta de saída (STL/3MF/STEP/PNG)."""
    out = runner.default_output_dir()
    if not out.exists():
        return _json({"output_dir": str(out), "files": []})
    files = sorted(
        (p for p in out.iterdir() if p.is_file() and p.suffix.lower() in (".stl", ".3mf", ".step", ".obj", ".fcstd", ".png")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    return _json({"output_dir": str(out), "files": [{"name": p.name, "kb": round(p.stat().st_size / 1024, 1)} for p in files]})


@mcp.tool()
def open_file(path: str) -> str:
    """Abre o arquivo no aplicativo padrão do sistema (ex.: 3MF → Bambu Studio, FCStd → FreeCAD)."""
    p = _resolve(path)
    if not p.exists():
        return _json({"ok": False, "error": f"Não existe: {p}"})
    try:
        if platform.system() == "Windows":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return _json({"ok": True, "opened": str(p)})
    except Exception as e:  # noqa: BLE001
        return _json({"ok": False, "error": str(e)})


def _resolve(path: str) -> Path:
    """Aceita caminho absoluto ou só o nome do arquivo (procura na pasta de saída)."""
    p = Path(path).expanduser()
    if p.exists():
        return p
    cand = runner.default_output_dir() / path
    return cand if cand.exists() else p


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
