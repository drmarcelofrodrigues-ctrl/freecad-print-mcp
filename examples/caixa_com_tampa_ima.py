# Caixinha com tampa fechada por 4 ímãs 5x2 — exemplo de shell + magnet_cavity.

L, W, H = 60.0, 40.0, 25.0
PAREDE = 2.0
R = 4.0
TAMPA_H = 4.0

corpo = awcad.rounded_box(L, W, H, r=R)
corpo = awcad.shell(corpo, PAREDE, open_top=True)
tampa = awcad.rounded_box(L, W, TAMPA_H, r=R)

# ímãs nos 4 cantos. A parede do corpo (2 mm) é mais fina que o ímã (5 mm), então
# primeiro engrossamos cada canto com uma coluna, depois cortamos a cavidade.
# No corpo o ímã entra pelo topo da parede; na tampa, pela face de baixo.
CANTOS = [(R + 1, R + 1), (L - R - 1, R + 1), (R + 1, W - R - 1), (L - R - 1, W - R - 1)]
envelope = awcad.rounded_box(L, W, H, r=R)
for x, y in CANTOS:
    coluna = awcad.common(awcad.move(awcad.cyl(8, H), x, y, 0), envelope)
    corpo = awcad.fuse(corpo, coluna)
    corpo = awcad.magnet_cavity(corpo, at=(x, y, H), d=5, h=2, axis=-awcad.Z)
    tampa = awcad.magnet_cavity(tampa, at=(x, y, 0), d=5, h=2, axis=awcad.Z)

awcad.export(awcad.chamfer_bottom(corpo), "caixa-corpo")
awcad.export(awcad.chamfer_bottom(tampa), "caixa-tampa")
