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


class CabecerasDeSeguridad:
    """Le dice al navegador qué tiene permitido hacer en nuestras páginas.

    El sistema no carga nada de afuera —ni tipografías, ni librerías, ni
    imágenes de otros sitios—, así que se le puede decir al navegador que
    **solo** acepte contenido propio. Si algún día alguien logra inyectar algo
    en una pantalla, esto le impide mandar los datos a otro servidor, meter la
    página dentro de un iframe ajeno o cambiar a dónde apunta un formulario.

    El `unsafe-inline` está porque el panel de Django y el portal usan estilos
    y scripts escritos dentro de la página. Es la parte floja de la política y
    conviene saberlo: lo que sí corta es la salida de datos hacia afuera.
    """

    POLITICA = "; ".join(
        [
            "default-src 'self'",
            "img-src 'self' data:",
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self' 'unsafe-inline'",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.setdefault("Content-Security-Policy", self.POLITICA)
        return respuesta
