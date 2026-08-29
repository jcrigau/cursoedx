"""Que el aviso del docente llegue y se pueda responder.

Cuando alguien avisa que falta, hoy eso dispara un llamado: «recibido,
acordate del certificado». Acá el aviso le llega a secretaría y dirección por
correo en el momento, queda al frente del tablero hasta que alguien lo
responda, y la respuesta sale con un toque: por la app (el docente ve «visto
por secretaría» en su portal), por WhatsApp o por correo, con el mensaje ya
escrito.

Sobre WhatsApp vale lo mismo que para avisarle a un suplente
(``licencias.avisos``): mandar sin intervención requiere la API paga de Meta;
abrir el chat con el mensaje escrito no cuesta nada.
"""

from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail

from core.correo import emails_de_gestion
from licencias.avisos import telefono_para_whatsapp

from .models import MotivoAviso


def asunto_para_gestion(aviso) -> str:
    return (
        f"{aviso.legajo.nombre_completo} avisa que falta el {aviso.fecha:%d/%m} "
        f"({aviso.get_motivo_display().lower()})"
    )


def mensaje_para_gestion(aviso, actualizado: bool = False) -> str:
    """El correo que reciben secretaría y dirección al llegar el aviso."""
    lineas = [
        f"{aviso.legajo.nombre_completo} "
        + ("actualizó su aviso" if actualizado else "avisó desde el portal")
        + f" que no va a poder asistir el {aviso.fecha:%d/%m/%Y}.",
        "",
        f"Motivo: {aviso.get_motivo_display()}.",
    ]
    if aviso.detalle:
        lineas.append(f"Detalle: {aviso.detalle}")
    lineas += [
        "",
        "Se responde desde el sistema, en «Avisos recibidos» (también está en el",
        "tablero de inicio): marcarlo visto se lo confirma en su portal, y los",
        "botones de WhatsApp y correo llevan el mensaje ya escrito.",
        "",
        "Si corresponde licencia, cargarla con su certificado; el aviso solo no",
        "justifica la falta.",
    ]
    return "\n".join(lineas)


def avisar_a_gestion(aviso, actualizado: bool = False) -> int:
    """Manda el aviso por correo a secretaría y dirección. Devuelve cuántos.

    Sin servidor de correo configurado no rompe nada: el aviso queda igual en
    el tablero, que es lo que no depende de nadie.
    """
    destinos = emails_de_gestion(aviso.institucion)
    if not destinos:
        return 0
    remitente = getattr(settings, "DEFAULT_FROM_EMAIL", "") or None
    return send_mail(
        subject=asunto_para_gestion(aviso),
        message=mensaje_para_gestion(aviso, actualizado),
        from_email=remitente,
        recipient_list=destinos,
        fail_silently=True,
    )


def respuesta_para(aviso) -> str:
    """La respuesta al docente, la misma vaya por WhatsApp o por correo."""
    texto = (
        f"Hola {aviso.legajo.nombre}, recibimos tu aviso del "
        f"{aviso.fecha:%d/%m} en {aviso.institucion}."
    )
    if aviso.motivo == MotivoAviso.ENFERMEDAD:
        texto += (
            " Acercanos el certificado médico cuando puedas, así te cargamos "
            "la licencia y la falta queda justificada."
        )
    else:
        texto += (
            " Si te corresponde licencia, acercanos el comprobante así la "
            "cargamos y la falta queda justificada."
        )
    texto += " ¡Que andes bien!"
    return texto


def link_whatsapp_respuesta(aviso) -> str:
    numero = telefono_para_whatsapp(aviso.legajo.telefono)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(respuesta_para(aviso))}"


def link_email_respuesta(aviso) -> str:
    if not aviso.legajo.email:
        return ""
    asunto = quote(f"Recibimos tu aviso del {aviso.fecha:%d/%m}")
    return f"mailto:{aviso.legajo.email}?subject={asunto}&body={quote(respuesta_para(aviso))}"
