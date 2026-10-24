# Referência da biblioteca awcad

Gerado a partir das docstrings de `src/freecad_print_mcp/fclib/awcad.py`. No chat, a ferramenta `awcad_reference` devolve o mesmo conteúdo.

```text
awcad — helpers de modelagem para impressão 3D, para rodar DENTRO do FreeCAD.

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

awcad.TOL = {'magnet': 0.15, 'press_fit': 0.05, 'slide_fit': 0.2, 'loose_fit': 0.4, 'hole_shrink': 0.2, 'min_wall': 1.2, 'elephant_foot': 0.4}

awcad.SCREWS = {'M2': {'through': 2.4, 'tap': 1.8, 'head_d': 3.8, 'head_h': 2.0}, 'M2.5': {'through': 2.9, 'tap': 2.2, 'head_d': 4.5, 'head_h': 2.5}, 'M3': {'through': 3.4, 'tap': 2.6, 'head_d': 5.7, 'head_h': 3.0}, 'M4': {'through': 4.5, 'tap': 3.4, 'head_d': 7.2, 'head_h': 4.0}, 'M5': {'through': 5.5, 'tap': 4.3, 'head_d': 8.7, 'head_h': 5.0}}

awcad.configure(output_dir: str, name: str)

awcad.note(msg: str)
    Anota uma observação que volta ao Claude no RESULT.

awcad.box(l: float, w: float, h: float, center: bool=False)
    Caixa l×w×h. Com center=True fica centrada em XY, base em Z=0.

awcad.cyl(d: float, h: float, center: bool=True)
    Cilindro de diâmetro d e altura h, eixo Z, base em Z=0. center=True → eixo na origem.

awcad.sphere(d: float, at=(0, 0, 0))

awcad.cone(d1: float, d2: float, h: float)

awcad.rounded_box(l: float, w: float, h: float, r: float, center: bool=False)
    Caixa com cantos verticais arredondados (raio r). Ótima como base de suportes.

awcad.wedge(l: float, w: float, h_front: float, h_back: float)
    Cunha/rampa: comprimento l (X), largura w (Y), altura h_front em X=0 e h_back em X=l.

awcad.polygon_prism(points: list, h: float)
    Prisma a partir de um polígono 2D [(x,y), ...] extrudado em Z.

awcad.move(s: Part.Shape, x=0.0, y=0.0, z=0.0)

awcad.rotate(s: Part.Shape, angle: float, axis=Z, center=(0, 0, 0))

awcad.mirror_x(s: Part.Shape)

awcad.fuse(*shapes: Part.Shape)

awcad.cut(base: Part.Shape, *tools: Part.Shape)

awcad.common(a: Part.Shape, b: Part.Shape)

awcad.on_bed(s: Part.Shape)
    Desloca a peça para que a face inferior fique em Z = 0.

awcad.center_xy(s: Part.Shape)

awcad.array(s: Part.Shape, n: int, pitch: float, axis=X)
    n cópias fundidas, espaçadas por pitch ao longo do eixo.

awcad.grid(s: Part.Shape, nx: int, ny: int, px: float, py: float)

awcad.magnet_cavity(base: Part.Shape, at, d: float=5.0, h: float=2.0, clearance: float | None=None, depth_extra: float=0.2, axis=Z, through: bool=False)
    Corta uma cavidade cilíndrica para ímã (padrão 5×2 mm).

at: ponto (x, y, z) do CENTRO DA BOCA da cavidade (face por onde o ímã entra).
axis: direção apontando para DENTRO da peça a partir da boca.
clearance: folga radial (padrão TOL['magnet']). depth_extra deixa o ímã 0,2 mm rebaixado.

awcad.hole(base: Part.Shape, at, d: float, depth: float | None=None, axis=Z, fdm_compensate: bool=True)
    Furo cilíndrico. at = centro na face de entrada; axis aponta para dentro.
fdm_compensate soma TOL['hole_shrink'] ao diâmetro (furos saem menores em FDM).

awcad.screw_hole(base: Part.Shape, at, size: str='M3', kind: str='through', depth: float | None=None, countersink: bool=False)
    Furo para parafuso métrico. kind: 'through' (passante com folga) ou 'tap' (rosquear no plástico).
countersink=True adiciona rebaixo para a cabeça (cabeça fica faceada), entrando por cima (-Z).

awcad.chamfer_bottom(s: Part.Shape, size: float | None=None)
    Chanfra todas as arestas da face inferior (anti pé de elefante).

awcad.fillet_vertical(s: Part.Shape, r: float)
    Arredonda todas as arestas verticais (cantos vistos de cima).

awcad.fillet_top(s: Part.Shape, r: float)

awcad.fillet_all(s: Part.Shape, r: float)

awcad.shell(s: Part.Shape, wall: float, open_top: bool=True)
    Transforma um sólido em casca com espessura wall. open_top remove a face superior (vira uma caixa aberta).

awcad.channel_round(base: Part.Shape, d: float, length: float, at, axis=X, open_ratio: float=1.0)
    Canaleta semicircular (berço) para tubo/seringa de diâmetro d, cortada a partir do topo.
at = ponto inicial do eixo do cilindro (centro da seção). open_ratio>1 alarga a boca.

awcad.ball_socket(d_ball: float, clearance: float=-0.05, wall: float=2.5, opening_ratio: float=0.88, slots: int=4, slot_width: float=1.0, slot_depth_ratio: float=0.7)
    Soquete para junta esférica, pensado para segurar pose em PLA.

Lições dos testes no A1: folga positiva (0,15–0,2) entra fácil mas não trava;
para articulação com atrito use folga ZERO ou NEGATIVA (interferência de ~0,05) com
fendas (slots) que deixam as paredes flexionarem. Esfera impressa com `ball()`.

Retorna um cilindro com a cavidade esférica aberta para +Z (boca em cima).
opening_ratio: diâmetro da boca / diâmetro da esfera (0,85–0,92 trava bem).

awcad.ball(d: float, stem_d: float | None=None, stem_h: float=4.0)
    Esfera para junta, com haste opcional por baixo (para fundir em outra peça).

awcad.text_label(base: Part.Shape, text: str, size: float=6.0, at=(0, 0, 0), depth: float=0.6, font: str | None=None, emboss: bool=False)
    Grava (ou eleva) texto na face superior em Z=at[2]. Precisa de uma fonte TTF.
No Windows: C:/Windows/Fonts/arial.ttf. Linux: /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

awcad.bbox(s: Part.Shape)
    Caixa envolvente justa (BoundBox padrão é folgado em superfícies curvas).

awcad.measure(s: Part.Shape, label: str='shape')

awcad.show(s: Part.Shape, label: str='Peca')
    Adiciona a shape ao documento (útil para salvar .FCStd).

awcad.export(s: Part.Shape, name: str | None=None, formats=('stl', '3mf'), linear_deflection: float=0.02, angular_deflection_deg: float=10.0, save_fcstd: bool=False)
    Exporta a shape. Mede, valida e grava STL/3MF/STEP em OUTPUT_DIR. Retorna caminhos.

linear_deflection 0,02 mm = malha fina (bom para peças pequenas e superfícies curvas).
```
