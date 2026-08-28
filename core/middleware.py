"""Middleware que resuelve la institución activa de cada request."""

from .tenancy import reset_institucion_actual, set_institucion_actual

CLAVE_SESION = "institucion_id"


class InstitucionActualMiddleware:
    """Deja en ``request.institucion`` la escuela sobre la que trabaja el usuario.

    La elección vive en la sesión: un usuario con membresías en varias escuelas
    (el caso del producto vendido a varias instituciones) las cambia sin volver
    a loguearse. Siempre se valida contra sus membresías, así una sesión vieja o
    un id manipulado no dan acceso a otra escuela.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        institucion = self._resolver(request)
        request.institucion = institucion
        token = set_institucion_actual(institucion)
        try:
            return self.get_response(request)
        finally:
            reset_institucion_actual(token)

    def _resolver(self, request):
        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            return None

        disponibles = usuario.instituciones()
        elegida_id = request.session.get(CLAVE_SESION)
        if elegida_id is not None:
            institucion = disponibles.filter(pk=elegida_id).first()
            if institucion is not None:
                return institucion

        institucion = disponibles.first()
        if institucion is not None:
            request.session[CLAVE_SESION] = institucion.pk
        elif CLAVE_SESION in request.session:
            del request.session[CLAVE_SESION]
        return institucion
