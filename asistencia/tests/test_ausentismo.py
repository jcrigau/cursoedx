"""El ausentismo, con los meses anteriores al lado.

Y una trampa que ya nos mordió: en es-AR los decimales se escriben con coma,
y un SVG con «x="65,9"» lee dos coordenadas en vez de una. El gráfico salía
roto en pantalla y verde en las pruebas.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from asistencia.ausentismo import por_mes, por_motivo
from asistencia.graficos import barras_apiladas
from asistencia.models import EstadoAsistencia, RegistroAsistencia


@pytest.fixture
def con_ausencias(institucion):
    """Una licencia de tres días y una ausencia sin licencia, este mes."""
    from legajos.models import Legajo
    from licencias.models import EstadoLicencia, Licencia, TipoLicencia

    legajo = Legajo.objects.create(
        institucion=institucion,
        apellido="Benítez",
        nombre="Ana",
        cuil="27-30000001-1",
        fecha_ingreso=date.today() - timedelta(days=500),
    )
    tipo = TipoLicencia.objects.create(
        institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
    )
    primero = date.today().replace(day=1)
    licencia = Licencia.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=tipo,
        fecha_inicio=primero,
        fecha_fin=primero + timedelta(days=2),
        estado=EstadoLicencia.APROBADA,
    )
    RegistroAsistencia.objects.create(
        institucion=institucion,
        legajo=legajo,
        fecha=date.today(),
        estado=EstadoAsistencia.AUSENTE,
    )
    return {"institucion": institucion, "legajo": legajo, "licencia": licencia}


@pytest.mark.django_db
class TestLasCuentas:
    def test_separa_licencia_de_inasistencia(self, con_ausencias):
        meses = por_mes(con_ausencias["institucion"], date.today())

        este_mes = meses[-1]
        assert len(meses) == 12
        assert este_mes.con_licencia == 3
        assert este_mes.sin_licencia == 1
        assert este_mes.total == 4

    def test_los_motivos_salen_ordenados(self, con_ausencias):
        meses = por_mes(con_ausencias["institucion"], date.today())

        motivos = por_motivo(con_ausencias["institucion"], meses)

        assert motivos[0][1] >= motivos[-1][1]
        assert any("Inasistencia sin licencia" == nombre for nombre, _ in motivos)

    def test_no_cuenta_lo_de_otra_escuela(self, con_ausencias, otra_institucion):
        meses = por_mes(otra_institucion, date.today())
        assert all(mes.total == 0 for mes in meses)


class TestElDibujo:
    def test_la_punta_de_la_barra_va_redondeada(self):
        grafico = barras_apiladas(
            [{"etiqueta": "ago", "titulo": "agosto", "valores": {"a": 2, "b": 3}}], ["a", "b"]
        )
        segmentos = grafico["columnas"][0].segmentos

        assert len(segmentos) == 2
        assert "a4,4" in segmentos[-1].ruta  # la de arriba lleva el arco
        assert "a4,4" not in segmentos[0].ruta  # la de abajo apoya recta

    def test_sin_datos_no_rompe(self):
        assert barras_apiladas([], ["a"])["columnas"] == []


@pytest.mark.django_db
class TestLaPantalla:
    def test_se_ve_con_los_numeros_al_lado(self, client, con_ausencias, secretaria):
        client.force_login(secretaria)

        cuerpo = client.get(reverse("ausentismo")).content.decode()

        assert "Ausentismo" in cuerpo
        # El gráfico y la tabla dicen lo mismo: nunca solo el color.
        assert "Con licencia" in cuerpo and "Sin licencia" in cuerpo
        assert "<svg" in cuerpo

    def test_las_coordenadas_del_svg_van_con_punto(self, client, con_ausencias, secretaria):
        """Con coma, el navegador lee dos coordenadas y el gráfico se rompe."""
        import re

        client.force_login(secretaria)
        cuerpo = client.get(reverse("ausentismo")).content.decode()
        svg = cuerpo[cuerpo.index("<svg") : cuerpo.index("</svg>")]

        assert not re.search(r'(x|y|x1|y1|x2|y2)="[-\d]+,\d', svg), (
            "hay coordenadas con coma decimal: falta {% localize off %}"
        )

    def test_no_es_publica(self, client, con_ausencias):
        assert client.get(reverse("ausentismo")).status_code in (302, 403)
