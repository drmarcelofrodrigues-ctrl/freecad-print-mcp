# freecad-print-mcp

Servidor [MCP](https://modelcontextprotocol.io) que deixa o Claude modelar peças para impressão 3D no **FreeCAD em modo headless** — sem abrir a interface — e checar se a peça vai imprimir bem antes de ir para o fatiador.

Pensado para peças funcionais em FDM (Bambu Lab A1 e similares): suportes, encaixes com ímã, juntas, caixas com tampa, acessórios de bancada.

## O que ele faz

| Ferramenta | Para quê |
|---|---|
| `freecad_run` | Executa um script Python no FreeCAD (`Part` + biblioteca `awcad`) e exporta STL/3MF/STEP |
| `freecad_run_file` | Roda um arquivo `.py` do disco (ex.: os de `examples/`) |
| `awcad_reference` | Documentação dos helpers `awcad` (cavidade de ímã, furos de parafuso, chanfro de base, junta esférica, casca, canaleta, matriz, texto…) |
| `mesh_render` | PNG com vistas iso/topo/frente/lado para o Claude "ver" a peça |
| `mesh_check_printability` | Malha fechada? Corpos soltos? % de área em balanço, contato com a mesa, melhor orientação |
| `mesh_measure` | Caixa envolvente, volume, massa estimada em PLA |
| `open_file` | Abre o 3MF no Bambu Studio (ou o app padrão) |
| `freecad_status` / `freecad_selftest` | Diagnóstico da instalação |

Diferença para o [freecad-mcp](https://github.com/neka-nat/freecad-mcp) (neka-nat): aquele controla o FreeCAD **aberto** via RPC e é ótimo para ver a árvore de objetos na GUI. Este roda **sem GUI**, cada chamada é um processo isolado e reprodutível (o script fica salvo em `_scripts/`), e o foco é o ciclo *modelar → ver → checar → fatiar*.

## Instalação

Pré-requisitos: FreeCAD 1.0+ instalado e Python 3.10+ (o Python do sistema, não o do FreeCAD).

**Windows, em um comando** (Win+R ou PowerShell) — clona em %LOCALAPPDATA%\freecad-print-mcp, instala, acha o FreeCAD e configura o Claude Desktop:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/drmarcelofrodrigues-ctrl/freecad-print-mcp/main/install.ps1 | iex"
```

**Manual:**

```bash
git clone https://github.com/drmarcelofrodrigues-ctrl/freecad-print-mcp
cd freecad-print-mcp
pip install -e .
```

Confira que o FreeCAD é encontrado:

```bash
python -c "from freecad_print_mcp import runner; print(runner.freecad_version())"
```

Se não encontrar, defina a variável `FREECAD_CMD` (Windows: `C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe`).

### Claude Desktop

Edite `claude_desktop_config.json` (Configurações → Desenvolvedor → Editar configuração) e adicione:

```json
{
  "mcpServers": {
    "freecad-print": {
      "command": "python",
      "args": ["-m", "freecad_print_mcp.server"],
      "env": {
        "FREECAD_CMD": "C:\\Program Files\\FreeCAD 1.0\\bin\\FreeCADCmd.exe",
        "FCMCP_OUTPUT_DIR": "C:\\Users\\SEU_USUARIO\\Documents\\Impressão 3D\\freecad-mcp"
      }
    }
  }
}
```

Reinicie o Claude Desktop e peça: *"rode o freecad_selftest"*. Detalhes e solução de problemas em [docs/instalacao-claude-desktop.md](docs/instalacao-claude-desktop.md).

### Claude Code

```bash
claude mcp add freecad-print -e FREECAD_CMD="..." -- python -m freecad_print_mcp.server
```

## Uso

Peça em linguagem natural; o Claude escreve o script, roda, renderiza e checa:

> *"Faz um suporte para 4 seringas de 10 mL inclinado 20°, com chanfro na base, e me mostra como ficou."*

O script que o Claude escreve se parece com isto:

```python
s = awcad.rounded_box(60, 40, 10, r=3, center=True)
s = awcad.magnet_cavity(s, at=(20, 0, 10), d=5, h=2, axis=-awcad.Z)   # ímã 5x2 entrando por cima
s = awcad.screw_hole(s, at=(-20, 0, 10), size="M3", countersink=True)
s = awcad.chamfer_bottom(s)                                           # anti pé-de-elefante
awcad.export(s, "base-com-ima")                                       # gera .stl e .3mf
```

Dentro do script estão disponíveis `App` (FreeCAD), `Part`, `doc` e `awcad`. Tudo em mm, Z para cima, base da peça em Z = 0.

Exemplos prontos em [`examples/`](examples/): suporte de seringas, placa de calibração de folgas, junta esférica, caixa com tampa magnética.

## Biblioteca `awcad`

Fica em `src/freecad_print_mcp/fclib/awcad.py` e é injetada em todo script. Resumo em [docs/api-awcad.md](docs/api-awcad.md). As tolerâncias padrão (`awcad.TOL`) são para PLA no A1 com bico 0,4 — imprima `examples/teste_folgas.py` e ajuste para o seu filamento.

## Boas práticas de modelagem para FDM

Leia [docs/boas-praticas-impressao.md](docs/boas-praticas-impressao.md): folgas, espessura mínima, orientação, pé de elefante, ímãs, juntas, quando usar STEP vs 3MF.

## Estrutura

```
src/freecad_print_mcp/
  server.py        # ferramentas MCP
  runner.py        # localiza e executa o FreeCADCmd
  mesh_tools.py    # análise e render de malha (trimesh)
  fclib/awcad.py   # helpers que rodam DENTRO do FreeCAD
examples/          # scripts prontos
docs/              # instalação, API, boas práticas
tests/             # testes do lado que não precisa do FreeCAD
```

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

Os testes cobrem `mesh_tools` e a montagem do script; a parte que depende do FreeCAD é testada pelo `freecad_selftest`.

## Licença

MIT — Marcelo Ferreira Rodrigues / AnestWorks.
