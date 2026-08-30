"""Avisarle al suplente que lo designaron.

Designar no es avisar. Hasta que alguien no lo llama, el suplente no sabe que
mañana tiene que estar, y la escuela no sabe si alguien lo llamó. Acá se arma
el mensaje una sola vez y se manda por donde se pueda.

Sobre WhatsApp: mandarlo solo, sin intervención, requiere la API de WhatsApp
Business de Meta —empresa verificada, plantillas aprobadas, y un costo por
conversación—. Eso es un trámite comercial, no código. Lo que sí se puede hacer
hoy y sin depender de nadie es dejar el mensaje escrito y abrir WhatsApp con un
toque: es un clic más y no cuesta nada.
"""

import re
from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail


def cargos_de_la_misma_suplencia(cobertura) -> list:
    """Todo lo que esa persona cubre de esa licencia, no solo un cargo.

    Cuando se designa a alguien para varios cargos de una licencia —tres
    cursos de la misma materia, por ejemplo—, avisarle de uno solo es peor que
    no avisarle: se presenta a una hora y falta a las otras dos.
    """
    from .models import Cobertura, TipoCobertura

    hermanas = (
        Cobertura.objects.filter(
            institucion=cobertura.institucion,
            licencia=cobertura.licencia,
            suplente=cobertura.suplente,
            tipo=TipoCobertura.SUPLENTE,
        )
        .select_related("cargo__materia", "cargo__curso")
        .order_by("cargo__materia__nombre", "cargo__curso__anio_estudio")
    )
    return [otra.cargo for otra in hermanas] or [cobertura.cargo]


def mensaje_para(cobertura) -> str:
    """El texto del aviso, el mismo vaya por donde vaya."""
    cargo = cobertura.cargo
    cargos = cargos_de_la_misma_suplencia(cobertura)
    if len(cargos) == 1:
        que_cubre = cargos[0].descripcion
    else:
        detalle = "\n".join(f"  · {otro.descripcion}" for otro in cargos)
        que_cubre = f"{len(cargos)} cargos:\n{detalle}\n"
    return (
        f"Hola {cobertura.suplente.nombre}, te escribimos de "
        f"{cobertura.institucion}.\n\n"
        f"Quedaste designado/a para cubrir {que_cubre}, "
        f"del {cobertura.fecha_inicio:%d/%m/%Y} al {cobertura.fecha_fin:%d/%m/%Y}, "
        f"en reemplazo de {cargo.legajo.nombre_completo}.\n\n"
        "Cualquier duda, respondé este mensaje.\n"
        "Muchas gracias."
    )


def asunto_para(cobertura) -> str:
    return f"Suplencia en {cobertura.institucion}: {cobertura.cargo.descripcion}"


def telefono_para_whatsapp(telefono: str) -> str:
    """Deja el número como lo espera wa.me: solo dígitos, con país.

    Los teléfonos se cargan como cada uno quiere —con guiones, con 0 y 15, con
    paréntesis—. Se limpia lo que sobra y se completa el 54 de Argentina si no
    está, que es lo que hace que el link abra el chat y no un error.
    """
    solo_digitos = re.sub(r"\D", "", telefono or "")
    if not solo_digitos:
        return ""
    # Formato local: 0 de larga distancia y 15 de celular no van en el
    # internacional.
    if solo_digitos.startswith("0"):
        solo_digitos = solo_digitos[1:]
    solo_digitos = re.sub(r"^(\d{2,4})15", r"\1", solo_digitos)
    if not solo_digitos.startswith("54"):
        solo_digitos = "54" + solo_digitos
    return solo_digitos


def link_de_whatsapp(cobertura) -> str:
    """El link que abre WhatsApp con el mensaje ya escrito."""
    numero = telefono_para_whatsapp(cobertura.suplente.telefono)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(mensaje_para(cobertura))}"


def enviar_por_email(cobertura) -> bool:
    """Manda el aviso por correo. Devuelve si se pudo.

    Sin servidor de correo configurado no falla la pantalla: lo dice y queda
    la opción de WhatsApp o el llamado.
    """
    if not cobertura.suplente.email:
        return False
    remitente = getattr(settings, "DEFAULT_FROM_EMAIL", "") or None
    enviados = send_mail(
        subject=asunto_para(cobertura),
        message=mensaje_para(cobertura),
        from_email=remitente,
        recipient_list=[cobertura.suplente.email],
        fail_silently=True,
    )
    return bool(enviados)
