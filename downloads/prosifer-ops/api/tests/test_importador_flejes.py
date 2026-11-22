import datetime as dt
from decimal import Decimal as D

from importador import flejes
from importador.flejes import (
    ConsumoMaquila, FilaConsolidadoFleje, LibroFlejes, OtSlitter, Rollo, SalidaFleje,
)

F = dt.date


def rollo(fila, codigo, peso, bobina="B1", fecha=F(2026, 1, 10), dueno="Prosifer"):
    return Rollo(fila, fecha, codigo, bobina, "LAM FRIO", "JIS", D("0.9"), D("268"), "1er-F", D(peso), dueno)


def ot(fila, numero, bobina="B1", fecha=F(2026, 1, 10)):
    return OtSlitter(fila, numero, bobina, fecha, "Total", D("1000"), D("8"), D("6"), 0, "1er-F", "Prosifer",
                     ((D("268"), D("994"), 2),))


def libro(rollos, ots=(), consumos=(), salidas=(), consolidado=(), entradas=()):
    return LibroFlejes(list(rollos), list(ots), list(consumos), list(salidas), list(consolidado), set(entradas))


def test_historia_de_un_rollo():
    lib = libro([rollo(4, "R1", "500")], [ot(5, 548)],
                [ConsumoMaquila(6, "314", "R1", D("200"), F(2026, 2, 1))],
                [SalidaFleje(7, "R1", D("100"), "Cliente", "Nota de Entrega Nro", "77", F(2026, 2, 5))])
    rp = flejes.construir(lib).rollos["R1"]
    assert rp.ot.numero == 548
    assert [m.tipo for m in rp.movimientos] == ["produccion", "consumo", "salida"]
    assert rp.saldo == D("200") and rp.estado == "disponible"


def test_oc_por_fecha_cuando_la_bobina_tuvo_varias():
    lib = libro([rollo(4, "R1", "500", fecha=F(2026, 3, 1))], [ot(5, 10, fecha=F(2026, 1, 1)), ot(6, 11, fecha=F(2026, 3, 1))])
    assert flejes.construir(lib).rollos["R1"].ot.numero == 11


def test_reenvio_queda_fusionado_y_agotado_en_flejes():
    lib = libro([rollo(4, "R1", "500")], [ot(5, 1)],
                salidas=[SalidaFleje(6, "R1", D("500"), "Prosifer", "Reenvio a Almacen Bobinas", "OC1", F(2026, 2, 1))],
                entradas={"R1"})
    rp = flejes.construir(lib).rollos["R1"]
    assert rp.fusionado and rp.saldo == 0


def test_liberacion_total_cambia_dueno_y_duplicada_cuenta_una_vez():
    sal = SalidaFleje(6, "R1", D("500"), "Nuevo", "Liberacion Nro", "9", F(2026, 2, 1))
    plan = flejes.construir(libro([rollo(4, "R1", "500")], [ot(5, 1)], salidas=[sal, sal]))
    assert plan.rollos["R1"].propietario == "Nuevo"
    assert "salida_duplicada" in [i.tipo for i in plan.incidencias]


def test_paridad_separa_lo_cortado_despues_del_consolidado():
    lib = libro([rollo(4, "R1", "500"), rollo(5, "R2", "300")], [ot(6, 1)],
                consolidado=[FilaConsolidadoFleje(4, "R1", D("500"), "Disponible", "Prosifer")])
    r = flejes.comparar(lib, flejes.construir(lib))
    assert r["diferencias"] == []
    assert [rp.rollo.codigo for rp in r["posteriores"]] == ["R2"]
    assert flejes.informe(r) is True
