"""Pantallas de asistencia: el parte del día y el resumen del mes."""

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from .models import EstadoAsistencia, RegistroAsistencia, buscar_licencia_que_justifica
from .parte import coberturas_pendientes, cuadro_del_dia, parte_diario
from .reportes import resumen_mensual

PERMISO_VER = "asistencia.view_registroasistencia"
PERMISO_CARGAR = "asistencia.add_registroasistencia"


def _fecha_pedida(request) -> date:
    crudo = request.GET.get("fecha") or request.POST.get("fecha")
    if not crudo:
        return date.today()
    try:
        return datetime.strptime(crudo, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


@login_required
@permission_required(PERMISO_VER, raise_exception=True)
def parte_del_dia(request):
    """Muestra quién debía trabajar hoy y permite marcar las novedades."""
    fecha = _fecha_pedida(request)

    if request.method == "POST":
        return _guardar_parte(request, fecha)

    parte = parte_diario(request.institucion, fecha)
    contexto = {
        "parte": parte,
        "fecha": fecha,
        "dia_anterior": fecha - timedelta(days=1),
        "dia_siguiente": fecha + timedelta(days=1),
        "hoy": date.today(),
        "estados": EstadoAsistencia.choices,
        "pendientes": coberturas_pendientes(request.institucion, fecha),
        "puede_cargar": request.user.has_perm(PERMISO_CARGAR),
    }
    return render(request, "asistencia/parte.html", contexto)


@permission_required(PERMISO_CARGAR, raise_exception=True)
def _guardar_parte(request, fecha: date):
    """Guarda lo marcado. Lo que queda en blanco se entiende como presente."""
    parte = parte_diario(request.institucion, fecha)
    guardados, borrados = 0, 0

    for linea in parte.lineas:
        legajo = linea.legajo
        estado = request.POST.get(f"estado_{legajo.id}", "").strip()
        existente = RegistroAsistencia.objects.filter(legajo=legajo, fecha=fecha).first()

        if not estado:
            if existente:
                existente.delete()
                borrados += 1
            continue

        horas = request.POST.get(f"horas_{legajo.id}", "").strip()
        observaciones = request.POST.get(f"obs_{legajo.id}", "").strip()

        registro = existente or RegistroAsistencia(
            institucion=request.institucion, legajo=legajo, fecha=fecha
        )
        registro.estado = estado
        registro.horas_afectadas = int(horas) if horas.isdigit() else None
        registro.observaciones = observaciones[:300]
        registro.registrado_por = request.user
        # Si la persona tiene licencia aprobada ese día, la ausencia queda
        # justificada sola: es el cruce que la secretaría hacía a mano.
        registro.licencia = (
            buscar_licencia_que_justifica(legajo, fecha) if registro.es_ausencia else None
        )
        registro.save()
        guardados += 1

    if guardados:
        messages.success(request, f"Se registraron {guardados} novedades del día.")
    if borrados:
        messages.info(request, f"Se quitaron {borrados} registros.")
    if not guardados and not borrados:
        messages.info(request, "No había novedades para guardar.")

    return HttpResponseRedirect(f"{reverse('parte_diario')}?fecha={fecha:%Y-%m-%d}")


@login_required
@permission_required(PERMISO_VER, raise_exception=True)
def resumen_del_mes(request):
    """Lo que se le va a informar a quien liquida, antes de armar las novedades."""
    hoy = date.today()
    try:
        anio = int(request.GET.get("anio", hoy.year))
        mes = int(request.GET.get("mes", hoy.month))
    except ValueError:
        anio, mes = hoy.year, hoy.month
    mes = min(max(mes, 1), 12)

    resumenes = resumen_mensual(request.institucion, anio, mes)
    contexto = {
        "resumenes": resumenes,
        "anio": anio,
        "mes": mes,
        "nombre_mes": date(anio, mes, 1),
        "meses": range(1, 13),
        "anios": range(hoy.year - 3, hoy.year + 2),
        "total_personas": len(resumenes),
    }
    return render(request, "asistencia/resumen.html", contexto)


@login_required
@permission_required(PERMISO_VER, raise_exception=True)
def cursos_del_dia(request):
    """El día visto por curso: qué se dicta en cada hora y quién la da.

    Es la mirada de preceptoría, la que el parte no da: el parte ordena por
    persona y responde "quién falta"; esta ordena por curso y responde "qué
    cursos se quedan sin clase, y a qué hora".
    """
    fecha = _fecha_pedida(request)
    cuadros = cuadro_del_dia(request.institucion, fecha)

    contexto = {
        "fecha": fecha,
        "hoy": date.today(),
        "dia_anterior": fecha - timedelta(days=1),
        "dia_siguiente": fecha + timedelta(days=1),
        "cuadros": cuadros,
        "horas_sin_clase": sum(cuadro.sin_clase for cuadro in cuadros),
        "cursos_afectados": sum(1 for cuadro in cuadros if cuadro.tiene_problemas),
        "parte": parte_diario(request.institucion, fecha) if not cuadros else None,
    }
    return render(request, "asistencia/cursos.html", contexto)
