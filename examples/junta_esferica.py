# Par esfera + soquete para testar articulação com atrito (bonecos articulados).
# Imprima os dois; o soquete com fendas flexiona e deve segurar a pose.
# Varie `clearance` entre -0.10 e +0.05 até achar o ponto de atrito ideal.

D = 11.0

soquete = awcad.ball_socket(D, clearance=-0.05, wall=2.5, opening_ratio=0.88, slots=4, slot_width=1.0)
esfera = awcad.ball(D, stem_d=5.0, stem_h=4.0)

awcad.export(soquete, "junta-soquete-11mm")
awcad.export(esfera, "junta-esfera-11mm")
