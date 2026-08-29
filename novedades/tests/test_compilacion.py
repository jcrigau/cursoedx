class TestDeDondeSalio:
    """Cada novedad automática tiene que poder explicar su origen."""

    def test_una_licencia_apunta_a_la_licencia(self):
        from novedades.models import Novedad, Origen

        novedad = Novedad(origen=Origen.AUTOMATICA, clave_origen="licencia:34:cargo:12")
        origen = novedad.de_donde_salio()

        assert "licencia" in origen["texto"]
        assert origen["url"].endswith("/admin/licencias/licencia/34/change/")

    def test_las_tardanzas_se_explican_aunque_no_tengan_un_registro_solo(self):
        """Salen de varios registros del mes, así que no hay uno al que ir."""
        from novedades.models import Novedad, Origen

        origen = Novedad(
            origen=Origen.AUTOMATICA, clave_origen="tardanzas:5:OFICIAL"
        ).de_donde_salio()

        assert origen["texto"]
        assert origen["url"] == ""

    def test_lo_cargado_a_mano_no_inventa_un_origen(self):
        from novedades.models import Novedad, Origen

        assert Novedad(origen=Origen.MANUAL, clave_origen="").de_donde_salio() is None
