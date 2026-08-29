"""Pantallas de novedades: revisión del mes, cierre y exportación."""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from core.models import AccionAuditada, registrar_auditoria
from core.pdf import responder_pdf

from .compilador import coberturas_del_mes, compilar
from .exportar import a_csv, a_xlsx, resumen_por_persona
from .models import MESES, EstadoPeriodo, Novedad, PeriodoNovedades, periodo_de

AYUDA_MES = [
    "<strong>Compilar se puede repetir.</strong> Cada novedad recuerda de qué "
    "hecho salió, así que actualiza en vez de duplicar, y no toca lo cargado a "
    "mano ni lo congelado por un cierre.",
    "Cada línea va a la planilla del <strong>cargo</strong> que la originó, no de "
    "la persona: quien tiene cargos de las dos fuentes genera dos líneas.",
    "Marcar «informadas» es una lista de control mientras se cargan en la planilla "
    "del liquidador; no cambia nada del cálculo.",
    "Hasta que el mes no se cierre, el liquidador no ve nada: un borrador todavía puede cambiar.",
]

PERMISO_VER = "novedades.view_novedad"
PERMISO_EDITAR = "novedades.change_novedad"


@login_required
@permission_required(PERMISO_VER, raise_exception=True)
def periodos(request):
    """Los meses cargados, con su estado y cuánto falta informar."""
    lista = PeriodoNovedades.objects.del_contexto()
    hoy = date.today()
    return render(
        request,
        "novedades/periodos.html",
        {
            "periodos": [{"periodo": p, "resumen": p.resumen()} for p in lista],
            "anio_actual": hoy.year,
            "mes_actual": hoy.month,
            "nombre_mes_actual": MESES[hoy.month - 1],
            "puede_editar": request.user.has_perm(PERMISO_EDITAR),
        },
    )


@login_required
@permission_required(PERMISO_VER, raise_exception=True)
def detalle(request, anio: int, mes: int):
    """Revisión del mes antes de informarlo, y cierre."""
    puede_editar = request.user.has_perm(PERMISO_EDITAR)

    if request.method == "POST":
        if not puede_editar:
            raise PermissionDenied
        return _accion(request, anio, mes)

    periodo = periodo_de(request.institucion, anio, mes, crear=puede_editar)
    if periodo is None:
        raise PermissionDenied("Ese período todavía no fue preparado.")
    # El liquidador solo ve lo que ya se cerró: un borrador puede cambiar.
    if not periodo.esta_cerrado and not puede_editar:
        raise PermissionDenied("El período todavía no está cerrado.")

    return render(
        request,
        "novedades/detalle.html",
        {
            "periodo": periodo,
            "ayuda": AYUDA_MES,
            "resumen": periodo.resumen(),
            "personas": resumen_por_persona(periodo),
            "sin_impacto": periodo.novedades.filter(impacta_haberes=False).count(),
            "suplencias": coberturas_del_mes(periodo),
            "puede_editar": puede_editar,
            "estados": EstadoPeriodo,
        },
    )


def _accion(request, anio: int, mes: int):
    periodo = periodo_de(request.institucion, anio, mes)
    accion = request.POST.get("accion", "")
    destino = f"{reverse('novedades_detalle', args=[anio, mes])}"

    if accion == "compilar":
        resultado = compilar(periodo, usuario=request.user)
        for aviso in resultado.avisos:
            messages.warning(request, aviso)
        if resultado.total:
            messages.success(
                request,
                f"{resultado.creadas} novedades nuevas y {resultado.actualizadas} actualizadas.",
            )
        elif not resultado.avisos:
            messages.info(request, "No hay novedades para compilar en este mes.")

    elif accion == "informadas":
        marcadas = 0
        for novedad in periodo.novedades.filter(pk__in=request.POST.getlist("novedad")):
            novedad.marcar_informada(usuario=request.user)
            marcadas += 1
        messages.success(request, f"Se marcaron {marcadas} novedades como informadas.")

    elif accion == "cerrar":
        pendientes = periodo.resumen()["pendientes"]
        if pendientes and not request.POST.get("confirmar"):
            messages.warning(
                request,
                f"Quedan {pendientes} novedades sin informar. Volvé a apretar Cerrar "
                "para confirmar de todos modos.",
            )
            return HttpResponseRedirect(f"{destino}?confirmar=1")
        periodo.cerrar(usuario=request.user)
        messages.success(request, f"{periodo} quedó cerrado.")

    elif accion == "reabrir":
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            messages.error(request, "Para reabrir el período hay que indicar el motivo.")
        else:
            periodo.reabrir(motivo, usuario=request.user)
            messages.success(request, f"{periodo} quedó reabierto.")

    return HttpResponseRedirect(destino)


@login_required
@permission_required(PERMISO_VER, raise_exception=True)
def exportar(request, anio: int, mes: int):
    """Descarga del paquete para pasarle al liquidador."""
    periodo = get_object_or_404(PeriodoNovedades.objects.del_contexto(), anio=anio, mes=mes)
    if not periodo.esta_cerrado and not request.user.has_perm(PERMISO_EDITAR):
        raise PermissionDenied("El período todavía no está cerrado.")

    formato = request.GET.get("formato", "xlsx")
    nombre = f"novedades-{periodo.anio}-{periodo.mes:02d}"

    registrar_auditoria(
        AccionAuditada.EXPORTACION,
        periodo,
        usuario=request.user,
        descripcion=f"Exportación de novedades de {periodo} ({formato})",
    )

    if formato == "csv":
        destino = request.GET.get("destino") or None
        respuesta = HttpResponse(a_csv(periodo, destino), content_type="text/csv; charset=utf-8")
        sufijo = f"-{destino.lower()}" if destino else ""
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}{sufijo}.csv"'
        return respuesta

    if formato == "pdf":
        html = render_to_string(
            "novedades/informe.html",
            {
                "periodo": periodo,
                "personas": resumen_por_persona(periodo),
                "resumen": periodo.resumen(),
                "emitido": timezone.now(),
                "emitido_por": request.user,
            },
            request=request,
        )
        return responder_pdf(html, request, nombre)

    contenido = a_xlsx(periodo)
    respuesta = HttpResponse(
        contenido,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.xlsx"'
    return respuesta


@login_required
@permission_required(PERMISO_EDITAR, raise_exception=True)
def alternar_informada(request, pk: int):
    """Marca o desmarca una novedad como ya cargada en la planilla."""
    novedad = get_object_or_404(Novedad.objects.del_contexto(), pk=pk)
    if novedad.informada:
        novedad.informada = False
        novedad.informada_en = None
        novedad.informada_por = None
        novedad.save(update_fields=["informada", "informada_en", "informada_por", "actualizado_en"])
    else:
        novedad.marcar_informada(usuario=request.user)
    return HttpResponseRedirect(
        reverse("novedades_detalle", args=[novedad.periodo.anio, novedad.periodo.mes])
    )
