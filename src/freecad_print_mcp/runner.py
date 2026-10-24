"""Localiza e executa o FreeCADCmd (FreeCAD headless) com um script Python.

O servidor MCP roda no Python do sistema; o FreeCAD tem seu próprio Python
embutido. Por isso nunca importamos FreeCAD aqui — escrevemos o script em um
arquivo temporário e chamamos o executável `FreeCADCmd`, lendo o resultado em
JSON que o script imprime no final.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

RESULT_MARKER = "__FCMCP_RESULT__"
LIB_DIR = Path(__file__).parent / "fclib"  # contém awcad.py (roda dentro do FreeCAD)


def default_output_dir() -> Path:
    env = os.environ.get("FCMCP_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Documents" / "FreeCAD-MCP"


def find_freecadcmd() -> str | None:
    """Procura o executável headless do FreeCAD.

    Ordem: variável FREECAD_CMD → PATH → locais padrão por sistema.
    """
    env = os.environ.get("FREECAD_CMD")
    if env and Path(env).exists():
        return env

    for name in ("FreeCADCmd", "freecadcmd", "FreeCADCmd.exe"):
        found = shutil.which(name)
        if found:
            return found

    patterns: list[str] = []
    system = platform.system()
    if system == "Windows":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if base:
                patterns.append(os.path.join(base, "FreeCAD*", "bin", "FreeCADCmd.exe"))
                patterns.append(os.path.join(base, "Programs", "FreeCAD*", "bin", "FreeCADCmd.exe"))
    elif system == "Darwin":
        patterns.append("/Applications/FreeCAD*.app/Contents/MacOS/FreeCADCmd")
        patterns.append(str(Path.home() / "Applications" / "FreeCAD*.app" / "Contents" / "MacOS" / "FreeCADCmd"))
    else:
        patterns += ["/usr/bin/freecadcmd", "/usr/local/bin/freecadcmd", "/snap/bin/freecad.cmd"]
        patterns.append(str(Path.home() / "Applications" / "FreeCAD*.AppImage"))

    candidates: list[str] = []
    for p in patterns:
        candidates += glob.glob(p)
    # Versão mais nova primeiro (ordenação por nome funciona para "FreeCAD 0.21" < "FreeCAD 1.0")
    candidates.sort(reverse=True)
    return candidates[0] if candidates else None


@dataclass
class RunResult:
    ok: bool
    returncode: int
    duration_s: float
    stdout: str
    stderr: str
    result: dict = field(default_factory=dict)
    script_path: str = ""

    def summary(self) -> dict:
        d = {
            "ok": self.ok,
            "returncode": self.returncode,
            "duration_s": round(self.duration_s, 2),
            "result": self.result,
        }
        if not self.ok:
            d["stderr"] = self.stderr[-4000:]
            d["stdout"] = self.stdout[-4000:]
        else:
            d["stdout"] = clean_stdout(self.stdout)[-3000:]
        return d


_NOISE_PREFIXES = ("FreeCAD ", "(C) 20", "FreeCAD is free", "saving.", RESULT_MARKER)


def clean_stdout(text: str) -> str:
    """Remove banner, barra de progresso e marcador de resultado; sobram os prints do usuário."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(_NOISE_PREFIXES):
            continue
        if s.startswith("(") and s.endswith("%)"):
            continue
        out.append(line.rstrip())
    return "\n".join(out)


def _bootstrap(output_dir: Path, name: str) -> str:
    return textwrap.dedent(
        f"""
        # --- bootstrap gerado pelo freecad-print-mcp ---
        import sys, json, traceback
        sys.path.insert(0, {str(LIB_DIR)!r})
        import FreeCAD as App
        import Part
        import awcad
        awcad.configure(output_dir={str(output_dir)!r}, name={name!r})
        RESULT = awcad.RESULT
        doc = App.newDocument("mcp")
        awcad.DOC = doc
        try:
        # --- código do usuário ---
        """
    )


def _epilogue() -> str:
    return textwrap.dedent(
        """
        # --- epílogo ---
            awcad._finish()
        except Exception:
            awcad.RESULT["error"] = traceback.format_exc()
        print("__FCMCP_RESULT__" + json.dumps(awcad.RESULT, default=str))
        """
    )


def build_script(user_code: str, output_dir: Path, name: str) -> str:
    body = textwrap.indent(textwrap.dedent(user_code), "    ")
    return _bootstrap(output_dir, name) + body + "\n" + _epilogue()


def run_script(
    user_code: str,
    name: str = "modelo",
    output_dir: Path | None = None,
    timeout: int = 180,
    keep_script: bool = True,
) -> RunResult:
    exe = find_freecadcmd()
    if not exe:
        return RunResult(
            ok=False,
            returncode=-1,
            duration_s=0,
            stdout="",
            stderr=(
                "FreeCADCmd não encontrado. Instale o FreeCAD 1.x ou defina a variável de "
                "ambiente FREECAD_CMD apontando para FreeCADCmd.exe "
                "(ex.: C:\\Program Files\\FreeCAD 1.0\\bin\\FreeCADCmd.exe)."
            ),
        )

    out = output_dir or default_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    script = build_script(user_code, out, name)

    scripts_dir = out / "_scripts"
    scripts_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    script_path = scripts_dir / f"{stamp}-{_slug(name)}.py"
    script_path.write_text(script, encoding="utf-8")

    kwargs: dict = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    t0 = time.time()
    try:
        proc = subprocess.run(
            [exe, str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            cwd=str(out),
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            ok=False, returncode=-2, duration_s=time.time() - t0, stdout="",
            stderr=f"FreeCADCmd excedeu {timeout}s. Simplifique o modelo ou aumente o timeout.",
            script_path=str(script_path),
        )
    dt = time.time() - t0

    result: dict = {}
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARKER):
            try:
                result = json.loads(line[len(RESULT_MARKER):])
            except json.JSONDecodeError:
                result = {"error": "Falha ao ler o JSON de resultado", "raw": line[:500]}

    ok = proc.returncode == 0 and "error" not in result and bool(result)
    rr = RunResult(
        ok=ok,
        returncode=proc.returncode,
        duration_s=dt,
        stdout=proc.stdout,
        stderr=proc.stderr if "error" not in result else result["error"],
        result=result,
        script_path=str(script_path),
    )
    if not keep_script and ok:
        script_path.unlink(missing_ok=True)
    return rr


def freecad_version() -> dict:
    exe = find_freecadcmd()
    if not exe:
        return {"found": False, "hint": "Defina FREECAD_CMD ou instale o FreeCAD 1.x"}
    code = (
        "import FreeCAD, json; v = FreeCAD.Version(); "
        "print('__V__' + json.dumps({'version': '.'.join(v[0:3]), 'build': v[3] if len(v) > 3 else ''}))"
    )
    try:
        proc = subprocess.run(
            [exe, "-c", code], capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("__V__"):
                info = json.loads(line[5:])
                return {"found": True, "exe": exe, **info}
        return {"found": True, "exe": exe, "warning": "Executou mas não retornou versão", "stderr": proc.stderr[-500:]}
    except Exception as e:  # noqa: BLE001
        return {"found": True, "exe": exe, "error": str(e)}


def _slug(s: str) -> str:
    keep = [c if c.isalnum() or c in "-_" else "-" for c in s.strip()]
    return "".join(keep).strip("-")[:40] or "modelo"


if __name__ == "__main__":  # uso rápido: python -m freecad_print_mcp.runner script.py
    code = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else "awcad.export(awcad.box(10,10,10))"
    print(json.dumps(run_script(code).summary(), indent=2, ensure_ascii=False))
