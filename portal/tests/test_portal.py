"""El portal del docente: cada uno ve lo suyo, y el fichaje registra dónde."""

from datetime import date, time, timedelta

import pytest

from core.models import Membresia, Rol, Usuario
from legajos.models import Legajo
from licencias.models import EstadoLicencia, Licencia, TipoLicencia
from portal.models import (
    AvisoInasistencia,
    EstadoAviso,
    Fichada,
    MotivoAviso,
    TipoFichada,
    distancia_en_metros,
)

from .conftest import LATITUD_ESCUELA, LONGITUD_ESCUELA

HOY = date.today()


class TestDistancia:
    def test_el_mismo_punto_da_cero(self):
        assert distancia_en_metros(-33.3, -66.3, -33.3, -66.3) == pytest.approx(0, abs=1)

    def test_un_grado_de_latitud_son_unos_111_km(self):
        distancia = distancia_en_metros(-33.0, -66.0, -34.0, -66.0)
        assert distancia == pytest.approx(111_000, rel=0.01)

    def test_cien_metros_aproximados(self):
        # 0.0009° de latitud son unos 100 m.
        distancia = distancia_en_metros(
            LATITUD_ESCUELA, LONGITUD_ESCUELA, LATITUD_ESCUELA + 0.0009, LONGITUD_ESCUELA
        )
        assert 90 < distancia < 110


@pytest.mark.django_db
class TestAcceso:
    def test_exige_login(self, client):
        respuesta = client.get("/portal/")
        assert respuesta.status_code == 302
        assert "/cuentas/login/" in respuesta["Location"]

    def test_un_usuario_sin_legajo_no_tiene_portal(self, client, escuela_ubicada):
        institucion = escuela_ubicada["institucion"]
        suelto = Usuario.objects.create_user(
            email="suelto@uno.edu.ar", password="x", nombre="Sin", apellido="Legajo"
        )
        Membresia.objects.create(usuario=suelto, institucion=institucion, rol=Rol.DOCENTE)

        client.force_login(suelto)
        respuesta = client.get("/portal/")
        assert respuesta.status_code == 403
        assert "no tenés legajo vinculado" in respuesta.content.decode().lower()

    def test_el_docente_entra_a_su_portal(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        respuesta = client.get("/portal/")
        assert respuesta.status_code == 200
        assert respuesta.context["legajo"] == docente_con_portal["legajo"]

    def test_solo_ve_su_propio_legajo(self, client, docente_con_portal, escuela_ubicada):
        """No hay forma de pedir el legajo de otro: se toma del usuario."""
        Legajo.objects.create(
            institucion=escuela_ubicada["institucion"],
            apellido="Otro",
            nombre="Docente",
            cuil="20-30999888-7",
        )
        client.force_login(docente_con_portal["usuario"])
        respuesta = client.get("/portal/legajo/")

        assert respuesta.context["legajo"] == docente_con_portal["legajo"]
        assert "Otro" not in respuesta.content.decode()

    def test_no_ve_el_portal_de_otra_escuela(self, client, docente_con_portal, otra_institucion):
        """Si el legajo es de otra institución, el portal no lo encuentra."""
        legajo = docente_con_portal["legajo"]
        legajo.institucion = otra_institucion
        legajo.save()

        client.force_login(docente_con_portal["usuario"])
        assert client.get("/portal/").status_code == 403


@pytest.mark.django_db
class TestFichaje:
    def _fichar(self, client, **datos):
        return client.post("/portal/fichar/", datos)

    def test_ficha_en_la_escuela(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        respuesta = self._fichar(
            client, latitud=LATITUD_ESCUELA, longitud=LONGITUD_ESCUELA, precision=12
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["ok"]
        fichada = Fichada.objects.get()
        assert fichada.en_la_escuela
        assert fichada.distancia_metros == 0

    def test_ficha_lejos_y_queda_marcado(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        # Un kilómetro al sur de la escuela.
        respuesta = self._fichar(client, latitud=LATITUD_ESCUELA + 0.009, longitud=LONGITUD_ESCUELA)

        cuerpo = respuesta.json()
        assert cuerpo["ok"]  # se registra igual
        assert not cuerpo["en_la_escuela"]
        fichada = Fichada.objects.get()
        assert not fichada.en_la_escuela
        assert fichada.distancia_metros > 200

    def test_ficha_sin_ubicacion(self, client, docente_con_portal):
        """Si el celular no da la ubicación, igual queda la constancia."""
        client.force_login(docente_con_portal["usuario"])
        respuesta = self._fichar(client)

        assert respuesta.json()["ok"]
        fichada = Fichada.objects.get()
        assert fichada.latitud is None
        assert not fichada.en_la_escuela

    def test_no_se_ficha_dos_veces_la_entrada(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        self._fichar(client, latitud=LATITUD_ESCUELA, longitud=LONGITUD_ESCUELA)
        respuesta = self._fichar(client, latitud=LATITUD_ESCUELA, longitud=LONGITUD_ESCUELA)

        assert respuesta.status_code == 409
        assert Fichada.objects.count() == 1

    def test_entrada_y_salida_son_marcas_distintas(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        self._fichar(client, tipo=TipoFichada.ENTRADA)
        self._fichar(client, tipo=TipoFichada.SALIDA)
        assert Fichada.objects.count() == 2

    def test_sin_ubicacion_de_la_escuela_no_se_puede_comparar(
        self, client, docente_con_portal, escuela_ubicada
    ):
        institucion = escuela_ubicada["institucion"]
        institucion.latitud = None
        institucion.longitud = None
        institucion.save()

        client.force_login(docente_con_portal["usuario"])
        self._fichar(client, latitud=LATITUD_ESCUELA, longitud=LONGITUD_ESCUELA)

        fichada = Fichada.objects.get()
        assert fichada.distancia_metros is None
        assert not fichada.en_la_escuela


@pytest.mark.django_db
class TestAvisos:
    def test_avisar_que_no_viene(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        client.post(
            "/portal/avisar/",
            {"fecha": f"{HOY:%Y-%m-%d}", "motivo": MotivoAviso.ENFERMEDAD, "detalle": "Gripe"},
        )

        aviso = AvisoInasistencia.objects.get()
        assert aviso.legajo == docente_con_portal["legajo"]
        assert aviso.motivo == MotivoAviso.ENFERMEDAD
        assert aviso.estado == EstadoAviso.ENVIADO

    def test_un_solo_aviso_por_dia(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        for motivo in (MotivoAviso.ENFERMEDAD, MotivoAviso.TRAMITE):
            client.post("/portal/avisar/", {"fecha": f"{HOY:%Y-%m-%d}", "motivo": motivo})

        assert AvisoInasistencia.objects.count() == 1
        assert AvisoInasistencia.objects.get().motivo == MotivoAviso.TRAMITE

    def test_no_se_avisa_para_un_dia_que_ya_paso(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        ayer = HOY - timedelta(days=1)
        client.post("/portal/avisar/", {"fecha": f"{ayer:%Y-%m-%d}", "motivo": MotivoAviso.OTRO})
        assert AvisoInasistencia.objects.count() == 0

    def test_se_puede_anular_mientras_no_lo_vieron(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        client.post("/portal/avisar/", {"fecha": f"{HOY:%Y-%m-%d}", "motivo": MotivoAviso.OTRO})
        aviso = AvisoInasistencia.objects.get()

        client.post(f"/portal/avisar/{aviso.pk}/anular/")
        aviso.refresh_from_db()
        assert aviso.estado == EstadoAviso.ANULADO

    def test_no_se_anula_un_aviso_ya_visto(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        client.post("/portal/avisar/", {"fecha": f"{HOY:%Y-%m-%d}", "motivo": MotivoAviso.OTRO})
        aviso = AvisoInasistencia.objects.get()
        aviso.marcar_visto()

        respuesta = client.post(f"/portal/avisar/{aviso.pk}/anular/")
        assert respuesta.status_code == 403

    def test_no_se_anula_el_aviso_de_otra_persona(
        self, client, docente_con_portal, escuela_ubicada
    ):
        ajeno = Legajo.objects.create(
            institucion=escuela_ubicada["institucion"],
            apellido="Ajeno",
            nombre="Juan",
            cuil="20-30999888-7",
        )
        aviso = AvisoInasistencia.objects.create(
            institucion=escuela_ubicada["institucion"],
            legajo=ajeno,
            fecha=HOY,
            motivo=MotivoAviso.OTRO,
        )
        client.force_login(docente_con_portal["usuario"])
        assert client.post(f"/portal/avisar/{aviso.pk}/anular/").status_code == 404


@pytest.mark.django_db
class TestSolicitudDeLicencia:
    def _tipo(self, institucion, **extra):
        datos = {"nombre": "Enfermedad", "codigo": "Art. 76", "con_goce": True}
        datos.update(extra)
        return TipoLicencia.objects.create(institucion=institucion, **datos)

    def test_la_solicitud_queda_pendiente(self, client, docente_con_portal, escuela_ubicada):
        tipo = self._tipo(escuela_ubicada["institucion"])
        client.force_login(docente_con_portal["usuario"])

        client.post(
            "/portal/licencias/",
            {
                "tipo": tipo.pk,
                "desde": f"{HOY:%Y-%m-%d}",
                "hasta": f"{HOY + timedelta(days=2):%Y-%m-%d}",
                "observaciones": "Reposo indicado",
            },
        )

        licencia = Licencia.objects.get()
        assert licencia.legajo == docente_con_portal["legajo"]
        assert licencia.estado == EstadoLicencia.SOLICITADA
        assert licencia.dias == 3

    def test_avisa_si_supera_el_tope(self, client, docente_con_portal, escuela_ubicada):
        tipo = self._tipo(
            escuela_ubicada["institucion"], nombre="Razones particulares", tope_dias_anual=5
        )
        client.force_login(docente_con_portal["usuario"])

        respuesta = client.post(
            "/portal/licencias/",
            {
                "tipo": tipo.pk,
                "desde": f"{HOY:%Y-%m-%d}",
                "hasta": f"{HOY + timedelta(days=9):%Y-%m-%d}",
            },
            follow=True,
        )

        assert Licencia.objects.count() == 0
        assert "tope" in respuesta.content.decode().lower()

    def test_rechaza_fechas_invertidas(self, client, docente_con_portal, escuela_ubicada):
        tipo = self._tipo(escuela_ubicada["institucion"])
        client.force_login(docente_con_portal["usuario"])

        client.post(
            "/portal/licencias/",
            {
                "tipo": tipo.pk,
                "desde": f"{HOY + timedelta(days=5):%Y-%m-%d}",
                "hasta": f"{HOY:%Y-%m-%d}",
            },
        )
        assert Licencia.objects.count() == 0

    def test_no_se_puede_pedir_con_un_tipo_de_otra_escuela(
        self, client, docente_con_portal, otra_institucion
    ):
        ajeno = TipoLicencia.objects.create(institucion=otra_institucion, nombre="Ajena")
        client.force_login(docente_con_portal["usuario"])

        respuesta = client.post(
            "/portal/licencias/",
            {"tipo": ajeno.pk, "desde": f"{HOY:%Y-%m-%d}", "hasta": f"{HOY:%Y-%m-%d}"},
        )
        assert respuesta.status_code == 404
        assert Licencia.objects.count() == 0


@pytest.mark.django_db
class TestParteConDatosDelPortal:
    def test_el_parte_muestra_el_aviso_y_la_fichada(self, docente_con_portal, escuela_ubicada):
        """Lo que el docente informa llega directo al parte de secretaría."""
        from asistencia.parte import parte_diario
        from horarios.generador import Parametros, generar
        from horarios.tests.conftest import (
            crear_curso,
            crear_esquema,
            crear_materia,
            crear_plan,
            crear_version,
            designar,
        )

        escuela = escuela_ubicada
        legajo = docente_con_portal["legajo"]
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 4)
        designar(escuela, legajo, materia, curso)
        version = crear_version(escuela)
        generar(version, Parametros(max_horas_dia_materia=4, segundos_limite=5))
        version.publicar()

        dias = sorted({a.dia_semana for a in version.asignaciones.all()})
        fecha = escuela["periodo"].fecha_inicio
        while fecha.weekday() not in dias:
            fecha += timedelta(days=1)

        AvisoInasistencia.objects.create(
            institucion=escuela["institucion"],
            legajo=legajo,
            fecha=fecha,
            motivo=MotivoAviso.ENFERMEDAD,
        )
        Fichada.objects.create(
            institucion=escuela["institucion"],
            legajo=legajo,
            fecha=fecha,
            hora=time(7, 50),
            latitud=LATITUD_ESCUELA,
            longitud=LONGITUD_ESCUELA,
        )

        parte = parte_diario(escuela["institucion"], fecha)
        linea = parte.lineas[0]
        assert linea.aviso is not None
        assert linea.aviso.motivo == MotivoAviso.ENFERMEDAD
        assert linea.fichada is not None
        assert linea.fichada.en_la_escuela
