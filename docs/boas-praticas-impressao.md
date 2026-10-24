# Boas práticas: modelar no FreeCAD para imprimir em FDM

Regras práticas para peças funcionais em PLA/PETG numa Bambu Lab A1 (bico 0,4 mm, camada 0,2 mm). Os números são pontos de partida — calibre com `examples/teste_folgas.py` e ajuste `awcad.TOL`.

## Folgas e encaixes

| Situação | Folga (por lado) | awcad |
|---|---|---|
| Ímã de neodímio 5×2 entrando à mão, firme | 0,10–0,15 mm | `magnet_cavity(..., clearance=0.15)` |
| Encaixe por pressão (press fit) | 0,05 mm | `TOL["press_fit"]` |
| Encaixe deslizante (tampa, gaveta) | 0,20 mm | `TOL["slide_fit"]` |
| Peça que gira livre (eixo em furo) | 0,30–0,40 mm | `TOL["loose_fit"]` |
| Furo passante para parafuso M3 | Ø 3,4 mm | `screw_hole(size="M3")` |
| Rosquear M3 direto no plástico | Ø 2,6 mm | `screw_hole(size="M3", kind="tap")` |

Furos saem **menores** do que o modelado (0,1–0,3 mm) por causa do arredondamento do perímetro: `hole()` já soma `TOL["hole_shrink"]`. Furos horizontais (eixo paralelo à mesa) saem achatados no topo — use furo em gota ou aumente 0,2 mm a mais.

## Espessuras

- Parede mínima estrutural: **1,2 mm** (3 perímetros). Paredes de 0,8 mm só para detalhe.
- Piso/teto mínimo: 4–5 camadas (0,8–1,0 mm).
- Pinos e colunas finas: Ø ≥ 3 mm, ou quebram no pós-processamento.
- Texto gravado: profundidade 0,4–0,6 mm, altura da letra ≥ 5 mm (`text_label`).

## Base e primeira camada

- **Pé de elefante**: a primeira camada esmaga e alarga 0,2–0,4 mm. Use `chamfer_bottom(0.4)` em tudo que encaixa em outra peça.
- Peça sempre com a base em Z = 0 (`on_bed()`); o `measure()` avisa se não estiver.
- Contato com a mesa: peças altas e estreitas tombam — `mesh_check_printability` avisa quando a razão altura/√área > 6.

## Orientação e balanços

- Balanço (overhang) até 45° imprime sem suporte; acima disso, ou use suporte, ou redesenhe (chanfro de 45° por baixo em vez de degrau reto).
- Pontes (bridges) até ~40 mm são OK em PLA.
- Furos horizontais > 8 mm: topo cai; modele como gota ou hexágono.
- `mesh_check_printability` testa 6 orientações e sugere a de menor balanço — mas a orientação também define a **resistência**: camadas são o ponto fraco, então pinos e abas devem ter as camadas atravessando o esforço, não paralelas a ele.

## Ímãs

- Cavidade 0,2 mm mais funda que o ímã (`depth_extra=0.2`) para o ímã ficar rebaixado e não raspar na outra peça.
- Em paredes finas (< 5 mm), engrosse localmente com uma coluna antes de cortar (ver `examples/caixa_com_tampa_ima.py`).
- Para ímã embutido (fechado dentro da peça), pause a impressão na camada certa no Bambu Studio — modele a cavidade com `through=False` e o teto acima dela com ≥ 0,8 mm.

## Juntas esféricas (bonecos articulados)

Lições dos testes no A1 com esfera de 11 mm:

- Folga positiva (0,15–0,20 mm) **entra fácil mas não segura pose**.
- Para atrito, use folga **zero ou negativa** (−0,05 a −0,10) **com fendas** no soquete (`ball_socket(slots=4)`): as paredes flexionam na montagem e apertam depois.
- Boca do soquete entre 85 e 92% do diâmetro da esfera.
- Imprima a esfera com camada de 0,12 mm para ficar mais lisa; ou lixe.
- Esfera e soquete em materiais diferentes (PLA + PETG) têm mais atrito que PLA + PLA.

## Canaletas e berços (seringas, tubos)

- Berço semicircular com o eixo a 50–60% do diâmetro afundado segura sem prender.
- Boca 2–4% mais larga que o diâmetro (`channel_round(open_ratio=1.03)`) facilita entrar.
- Para seringas, meça o **corpo** (não a aba): 10 mL ≈ 16 mm, 20 mL ≈ 20–21 mm, 60 mL ≈ 30 mm — varia por marca.

## Exportação

- **STL** para fatiar: `linear_deflection=0.02` é fino o suficiente; 0,05 para peças grandes.
- **3MF** é o que o Bambu Studio prefere; o 3MF do FreeCAD é só geometria (sem metadados de projeto).
- **STEP** para guardar o modelo editável ou mandar para usinagem; `formats=("stl", "3mf", "step")`.
- Sempre rode `mesh_check_printability` no STL exportado: `watertight=False` quase sempre vem de booleanas mal resolvidas — um `removeSplitter()` (já feito em `fuse`/`cut`) ou um pequeno deslocamento de 0,01 mm nas ferramentas de corte resolve.

## Fluxo recomendado no chat

1. Descreva a peça com medidas e o que ela precisa encaixar.
2. Claude escreve o script `awcad` e roda `freecad_run`.
3. `mesh_render` para conferir visualmente; ajuste parâmetros.
4. `mesh_check_printability` → orientação e avisos.
5. `open_file` no 3MF → Bambu Studio → imprimir.
6. Mediu algo diferente do esperado? Ajuste `awcad.TOL` ou passe `clearance=` explícito.
