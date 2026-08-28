"""El aislamiento entre escuelas es el invariante que no puede fallar.

Si una consulta cruzara datos, una escuela vería los legajos o las licencias de
otra. Estas pruebas cubren las tres capas donde eso podría pasar: los managers,
el middleware que elige la institución y el admin.
"""

import pytest

from core.middleware import CLAVE_SESION, InstitucionActualMiddleware
from core.models import Membresia, RegistroAuditoria, Rol, Usuario, registrar_auditoria
from core.tenancy import get_institucion_actual, usar_institucion
from estructura.models import Nivel, TipoNivel


@pytest.fixture
def niveles(institucion, otra_institucion):
    return {
        "uno": Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO),
        "dos": Nivel.objects.create(institucion=otra_institucion, tipo=TipoNivel.SECUNDARIO),
    }


class TestManagers:
    def test_del_contexto_devuelve_solo_la_institucion_activa(self, institucion, niveles):
        with usar_institucion(institucion):
            assert list(Nivel.objects.del_contexto()) == [niveles["uno"]]

    def test_sin_contexto_no_devuelve_nada(self, niveles):
        # Un olvido de contexto no puede terminar mostrando datos de otra escuela.
        assert Nivel.objects.del_contexto().count() == 0

    def test_objects_sin_filtrar_sigue_viendo_todo(self, niveles):
        # Necesario para migraciones, comandos y soporte.
        assert Nivel.objects.count() == 2

    def test_el_contexto_se_restaura_al_salir(self, institucion):
        with usar_institucion(institucion):
            assert get_institucion_actual() == institucion
        assert get_institucion_actual() is None


class TestMiddleware:
    def _procesar(self, rf, usuario, sesion=None):
        peticion = rf.get("/")
        peticion.user = usuario
        peticion.session = sesion if sesion is not None else {}
        capturado = {}

        def siguiente(request):
            capturado["institucion"] = get_institucion_actual()
            capturado["request"] = request.institucion
            return "respuesta"

        InstitucionActualMiddleware(siguiente)(peticion)
        return capturado, peticion.session

    def test_elige_la_institucion_del_usuario(self, rf, secretaria, institucion):
        capturado, sesion = self._procesar(rf, secretaria)
        assert capturado["institucion"] == institucion
        assert sesion[CLAVE_SESION] == institucion.pk

    def test_ignora_una_institucion_ajena_en_la_sesion(
        self, rf, secretaria, institucion, otra_institucion
    ):
        # Una sesión manipulada no puede dar acceso a otra escuela.
        capturado, _ = self._procesar(rf, secretaria, {CLAVE_SESION: otra_institucion.pk})
        assert capturado["institucion"] == institucion

    def test_usuario_sin_membresias_no_tiene_institucion(self, rf, db):
        suelto = Usuario.objects.create_user(
            email="suelto@ejemplo.com", password="x", nombre="Sin", apellido="Acceso"
        )
        capturado, _ = self._procesar(rf, suelto)
        assert capturado["institucion"] is None

    def test_limpia_el_contexto_al_terminar(self, rf, secretaria):
        self._procesar(rf, secretaria)
        assert get_institucion_actual() is None


class TestPermisosDeUsuario:
    def test_roles_por_institucion(self, secretaria, institucion, otra_institucion):
        assert secretaria.tiene_rol(institucion, Rol.SECRETARIA)
        # El mismo rol no se hereda a otra escuela.
        assert not secretaria.tiene_rol(otra_institucion, Rol.SECRETARIA)

    def test_membresia_inactiva_no_da_acceso(self, secretaria, institucion):
        Membresia.objects.filter(usuario=secretaria).update(activa=False)
        assert secretaria.instituciones().count() == 0

    def test_superusuario_ve_todas_las_instituciones(self, db, institucion, otra_institucion):
        jefe = Usuario.objects.create_superuser(
            email="admin@sge.ar", password="x", nombre="Admin", apellido="SGE"
        )
        assert jefe.instituciones().count() == 2


class TestAuditoria:
    def test_registrar_toma_datos_del_objeto(self, institucion, secretaria, niveles):
        registro = registrar_auditoria(
            "CREACION", niveles["uno"], usuario=secretaria, descripcion="alta de nivel"
        )
        assert registro.institucion == institucion
        assert registro.modelo == "Nivel"
        assert registro.objeto_id == str(niveles["uno"].pk)

    def test_no_se_puede_modificar(self, institucion):
        registro = registrar_auditoria("CIERRE_PERIODO", institucion=institucion)
        registro.descripcion = "otra cosa"
        with pytest.raises(ValueError):
            registro.save()

    def test_no_se_puede_borrar(self, institucion):
        registro = registrar_auditoria("CIERRE_PERIODO", institucion=institucion)
        with pytest.raises(ValueError):
            registro.delete()
        assert RegistroAuditoria.objects.count() == 1
