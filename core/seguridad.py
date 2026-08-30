"""Defensa del ingreso: quién entró, quién falló, y cuándo frenar.

Una escuela es un blanco fácil y aburrido: nadie va a montar un ataque
sofisticado, pero cualquiera con tiempo puede probar contraseñas contra la
dirección del sistema hasta acertar una. Sin freno, eso funciona.

La regla es simple y no deja a nadie afuera para siempre: después de varios
intentos fallidos seguidos, esa dirección desde esa computadora espera unos
minutos. Un ataque con muchas direcciones distintas se corta con un tope más
alto por IP.

Un dato importante para el que lee esto: el mensaje que ve la persona **nunca
dice si el email existe**. Decirlo le regala al atacante la mitad del trabajo.
"""

from datetime import timedelta

from django.utils import timezone

# Intentos fallidos de una misma dirección desde una misma IP antes de frenar.
INTENTOS_MAXIMOS = 5
# Fallos desde una misma IP contra cualquier dirección: un barrido.
INTENTOS_MAXIMOS_POR_IP = 20
VENTANA = timedelta(minutes=15)
ESPERA = timedelta(minutes=15)


def ip_de(request) -> str | None:
    """La IP de quien pide, mirando el encabezado del proxy si lo hay."""
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        # El primero de la lista es el cliente; el resto son los proxies.
        return reenviada.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def registrar_intento(email: str, ip: str | None, exito: bool):
    from .models import IntentoDeAcceso

    IntentoDeAcceso.objects.create(email=(email or "")[:254], ip=ip, exito=exito)


def _fallos_desde(desde, **filtros) -> int:
    from .models import IntentoDeAcceso

    return IntentoDeAcceso.objects.filter(exito=False, creado_en__gte=desde, **filtros).count()


def minutos_de_espera(email: str, ip: str | None) -> int:
    """Cuántos minutos falta esperar, o 0 si puede intentar.

    Se cuentan los fallos desde el último ingreso exitoso: entrar bien limpia
    la cuenta, así el que se equivocó dos veces y después entró no arrastra
    nada.
    """
    from .models import IntentoDeAcceso

    ahora = timezone.now()
    desde = ahora - VENTANA

    ultimo_exito = (
        IntentoDeAcceso.objects.filter(email=email, exito=True, creado_en__gte=desde)
        .order_by("-creado_en")
        .first()
    )
    if ultimo_exito is not None:
        desde = ultimo_exito.creado_en

    por_persona = _fallos_desde(desde, email=email, ip=ip) if email else 0
    por_maquina = _fallos_desde(ahora - VENTANA, ip=ip) if ip else 0

    if por_persona < INTENTOS_MAXIMOS and por_maquina < INTENTOS_MAXIMOS_POR_IP:
        return 0

    ultimo = IntentoDeAcceso.objects.filter(exito=False, ip=ip).order_by("-creado_en").first()
    if ultimo is None:
        return 0
    faltan = (ultimo.creado_en + ESPERA) - ahora
    return max(0, int(faltan.total_seconds() // 60) + 1)
