# Suporte inclinado para 3 seringas de 20 mL — versão FreeCAD do modelo que já foi
# impresso com sucesso em OpenSCAD. Rode com a ferramenta freecad_run_file ou:
#   FreeCADCmd examples/suporte_seringas_20ml.py   (precisa do bootstrap; use o MCP)
#
# Parâmetros (mm)
N = 3                # seringas
D_SERINGA = 20.6     # diâmetro externo do corpo da seringa 20 mL (medido) + folga
L_BERCO = 60.0       # comprimento do berço
PITCH = 28.0         # distância entre centros
ANGULO = 20.0        # inclinação da rampa (bico para cima)
PAREDE = 3.0
H_FRENTE = 8.0       # altura do bloco na frente (ponta do bico)
RASGO_ABA = 1.6      # rasgo para a aba da seringa apoiar
PROF_BERCO = 0.55    # fração do diâmetro que fica afundada no berço

import math

larg = N * PITCH
h_tras = H_FRENTE + L_BERCO * math.tan(math.radians(ANGULO))
bloco = awcad.wedge(L_BERCO, larg, h_tras, H_FRENTE)   # mais alto em X=0 (fundo), mais baixo em X=L (bico)

# berços inclinados: cilindro ao longo da rampa
for i in range(N):
    y = PITCH / 2 + i * PITCH
    # eixo do berço paralelo à superfície da rampa, afundado PROF_BERCO*D
    z0 = h_tras - D_SERINGA * PROF_BERCO
    # rotação de +θ em torno de Y leva Z → (sinθ, 0, cosθ): com θ = 90+ANGULO o eixo desce junto com a rampa
    tool = awcad.cyl(D_SERINGA, L_BERCO + 20, center=True)           # eixo Z
    tool = awcad.rotate(tool, 90 + ANGULO, axis=awcad.Y)             # deita ao longo da rampa (descendo em X)
    tool = awcad.move(tool, x=-5, y=y, z=z0 + 5 * math.tan(math.radians(ANGULO)))
    # abertura até o topo (bloco sobre o berço): rotação +θ leva X → (cosθ, 0, -sinθ)
    topo = awcad.box(L_BERCO + 20, D_SERINGA * 0.98, 60)
    topo = awcad.rotate(topo, ANGULO, axis=awcad.Y)
    topo = awcad.move(topo, x=-5, y=y - D_SERINGA * 0.49, z=z0 + 5 * math.tan(math.radians(ANGULO)))
    bloco = awcad.cut(bloco, tool, topo)
    # rasgo para a aba do êmbolo na ponta BAIXA (X≈L): com o bico para cima a aba fica embaixo e trava a seringa
    rasgo = awcad.box(RASGO_ABA + 0.3, D_SERINGA + 8, 40)
    rasgo = awcad.move(rasgo, x=L_BERCO - 8, y=y - (D_SERINGA + 8) / 2, z=2)
    bloco = awcad.cut(bloco, rasgo)

bloco = awcad.on_bed(bloco)
bloco = awcad.chamfer_bottom(bloco)
awcad.note(f"suporte {N}x seringa 20 mL, rampa {ANGULO}°, {larg:.0f} x {L_BERCO:.0f} mm")
awcad.export(bloco, "suporte-3-seringas-20ml", formats=("stl", "3mf"))
