"""Vistas de consulta e impresión de horarios."""

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from core.pdf import responder_pdf
from estructura.models import Curso
from legajos.models import Legajo

from .models import VersionHorario
from .vistas_grilla import grilla_de_curso, grilla_de_docente

PERMISO = "horarios.view_versionhorario"


def _version_de(request, pk) -> VersionHorario:
    return get_object_or_404(
        VersionHorario.objects.del_contexto().select_related("periodo__ciclo"), pk=pk
    )


@login_required
@permission_required(PERMISO, raise_exception=True)
def version(request, pk):
    """Índice de la versión: cursos, docentes y estado de la generación."""
    version_horario = _version_de(request, pk)
    asignaciones = version_horario.asignaciones.select_related("curso", "legajo")

    cursos = sorted(
        {asignacion.curso for asignacion in asignaciones},
        key=lambda curso: (curso.nivel_id, curso.anio_estudio, curso.division),
    )
    dias_por_docente = version_horario.dias_por_docente()
    docentes = sorted(dias_por_docente.items(), key=lambda par: par[0].nombre_completo)

    horas_por_docente = {}
    for asignacion in asignaciones:
        if asignacion.legajo_id:
            horas_por_docente[asignacion.legajo_id] = (
                horas_por_docente.get(asignacion.legajo_id, 0) + 1
            )

    contexto = {
        "version": version_horario,
        "cursos": cursos,
        "docentes": [
            {"legajo": legajo, "dias": dias, "horas": horas_por_docente.get(legajo.id, 0)}
            for legajo, dias in docentes
        ],
        "sin_docente": asignaciones.filter(legajo__isnull=True).count(),
        "resumen": version_horario.resumen,
    }
    return render(request, "horarios/version.html", contexto)


@login_required
@permission_required(PERMISO, raise_exception=True)
def grilla_curso(request, pk, curso_id):
    version_horario = _version_de(request, pk)
    curso = get_object_or_404(
        Curso.objects.del_contexto().select_related("nivel", "turno", "esquema_horario"),
        pk=curso_id,
    )
    return _responder(request, version_horario, grilla_de_curso(version_horario, curso))


@login_required
@permission_required(PERMISO, raise_exception=True)
def grilla_docente(request, pk, legajo_id):
    version_horario = _version_de(request, pk)
    legajo = get_object_or_404(Legajo.objects.del_contexto(), pk=legajo_id)
    return _responder(request, version_horario, grilla_de_docente(version_horario, legajo))


def _responder(request, version_horario, grilla):
    contexto = {"grilla": grilla, "version": version_horario}
    if request.GET.get("formato") != "pdf":
        return render(request, "horarios/grilla.html", contexto)

    html = render_to_string("horarios/grilla.html", contexto, request=request)
    return responder_pdf(html, request, f"horario-{grilla.titulo}")
