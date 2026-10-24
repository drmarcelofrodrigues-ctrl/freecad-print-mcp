# Instalação no Claude Desktop (Windows)

## 1. FreeCAD

Instale o FreeCAD 1.0 ou mais novo (instalador `.exe` do site oficial ou `winget install FreeCAD.FreeCAD`). O executável headless fica em:

```
C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe
```

Teste no PowerShell:

```powershell
& "C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe" -c "import FreeCAD; print(FreeCAD.Version())"
```

## 2. Python e o servidor

Use o Python do sistema (3.10+), não o embutido no FreeCAD.

```powershell
git clone https://github.com/drmarcelofrodrigues-ctrl/freecad-print-mcp
cd freecad-print-mcp
pip install -e .
python -c "from freecad_print_mcp import runner; print(runner.freecad_version())"
```

Saída esperada: `{'found': True, 'exe': 'C:\\Program Files\\FreeCAD 1.0\\bin\\FreeCADCmd.exe', 'version': '1.0.2', ...}`.

## 3. Configuração do Claude Desktop

Abra **Configurações → Desenvolvedor → Editar configuração** (abre a pasta com `claude_desktop_config.json`). Adicione o bloco abaixo dentro de `mcpServers`, mantendo os servidores que já existem (ex.: `openscad`):

```json
"freecad-print": {
  "command": "python",
  "args": ["-m", "freecad_print_mcp.server"],
  "env": {
    "FREECAD_CMD": "C:\\Program Files\\FreeCAD 1.0\\bin\\FreeCADCmd.exe",
    "FCMCP_OUTPUT_DIR": "C:\\Users\\SEU_USUARIO\\Documents\\Impressão 3D\\freecad-mcp"
  }
}
```

Se `python` não estiver no PATH do Claude Desktop, use o caminho completo (`C:\\Users\\SEU_USUARIO\\AppData\\Local\\Programs\\Python\\Python312\\python.exe`). Descubra com `where python` no PowerShell.

Reinicie o Claude Desktop (fechar pela bandeja do sistema, não só a janela). O ícone de ferramentas deve listar `freecad-print`.

## 4. Primeiro teste

No chat: **"rode o freecad_selftest"**. Deve voltar `ok: true`, com medidas e os caminhos de `selftest.stl` e `selftest.3mf`. Depois: **"renderize o selftest.stl"**.

## Variáveis de ambiente

| Variável | Função | Padrão |
|---|---|---|
| `FREECAD_CMD` | Caminho do `FreeCADCmd` | busca automática em `Program Files` |
| `FCMCP_OUTPUT_DIR` | Pasta onde STL/3MF/scripts são gravados | `~/Documents/FreeCAD-MCP` |

## Problemas comuns

**`FreeCADCmd não encontrado`** — confira o caminho em `FREECAD_CMD`; a pasta pode se chamar `FreeCAD 1.0` ou `FreeCAD 1.1`.

**Servidor não aparece no Claude Desktop** — JSON inválido (vírgula a mais) ou `python` não encontrado. Teste o comando no PowerShell: `python -m freecad_print_mcp.server` deve ficar rodando em silêncio (Ctrl+C para sair).

**`ModuleNotFoundError: mcp`** — o `pip install -e .` foi feito em outro Python. Use o mesmo `python` que está no JSON.

**Timeout** — modelos com muitos fillets/booleanas podem passar de 180 s; peça ao Claude para usar `timeout_s` maior ou simplificar.

**3MF não abre no Bambu Studio** — o 3MF do FreeCAD é "só malha" (sem metadados de projeto); o Bambu Studio importa como geometria. Se preferir, use o STL.

## Claude Code (terminal)

```bash
claude mcp add freecad-print -e FREECAD_CMD="C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe" -- python -m freecad_print_mcp.server
```
