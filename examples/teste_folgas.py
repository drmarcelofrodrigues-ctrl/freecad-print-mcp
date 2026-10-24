# Placa de calibração de folgas para o seu filamento/impressora.
# Imprima uma vez, teste cada furo com um ímã 5x2 e um pino de 5 mm, e ajuste awcad.TOL.
#
# Linha de cima: furos para ímã 5 mm com folgas radiais de 0,00 a 0,30 (passo 0,05)
# Linha de baixo: furos passantes de 5 mm com compensação FDM de 0,0 a 0,4

FOLGAS = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
PITCH = 10.0
placa = awcad.rounded_box(len(FOLGAS) * PITCH + 4, 26, 4, r=2)

for i, f in enumerate(FOLGAS):
    x = 2 + PITCH / 2 + i * PITCH
    placa = awcad.magnet_cavity(placa, at=(x, 19, 4), d=5, h=2, clearance=f, axis=-awcad.Z)
    placa = awcad.hole(placa, at=(x, 7, 4), d=5 + f, axis=-awcad.Z, fdm_compensate=False)

placa = awcad.text_label(placa, "0  .05 .1 .15 .2 .25 .3", size=2.6, at=(3, 12, 4), depth=0.4)
placa = awcad.chamfer_bottom(placa, 0.3)
awcad.export(placa, "teste-folgas-5mm")
