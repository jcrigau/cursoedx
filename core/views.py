"""Vistas base: tablero de inicio y cambio de institución."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .bienvenida import para as bienvenida_para
from .middleware import CLAVE_SESION
from .models import Rol
from .pendientes import pendientes_de
from .version import informacion


@login_required
def inicio(request):
    """Tablero de entrada.

    Hoy resume la estructura cargada; a medida que avancen las fases va a
    mostrar también vencimientos, licencias en curso y novedades pendientes
    (módulo M7 del documento de requerimientos).
    """
    institucion = request.institucion
    if institucion is None:
        return render(request, "core/sin_institucion.html", status=403)

    # El docente no trabaja sobre el tablero de la escuela: lo suyo está en el
    # portal. Se lo lleva directo en lugar de mostrarle una pantalla vacía.
    if _solo_es_docente(request.user, institucion):
        return HttpResponseRedirect(reverse("portal_inicio"))

    # Import local: el tablero cruza módulos y va a sumar más apps por fase.
    from estructura.models import (
        BloqueHorario,
        CicloLectivo,
        Curso,
        EstadoCiclo,
        Materia,
        Nivel,
        TipoBloque,
    )

    ciclo = (
        CicloLectivo.objects.del_contexto().filter(estado=EstadoCiclo.ACTIVO).first()
        or CicloLectivo.objects.del_contexto().first()
    )
    cursos = Curso.objects.del_contexto()
    if ciclo is not None:
        cursos = cursos.filter(ciclo_lectivo=ciclo)

    contexto = {
        "ciclo": ciclo,
        "cantidad_niveles": Nivel.objects.del_contexto().count(),
        "cantidad_cursos": cursos.count(),
        "cantidad_materias": Materia.objects.del_contexto().count(),
        "periodos": list(ciclo.periodos.all()) if ciclo else [],
        "tiene_grilla": BloqueHorario.objects.filter(
            esquema__institucion=institucion, tipo=TipoBloque.CLASE
        ).exists(),
        "cursos": cursos.select_related("nivel", "turno", "esquema_horario")[:12],
    }
    personal = _resumen_de_personal(institucion)
    situacion = _situacion_del_dia(institucion)
    contexto.update(personal)
    contexto.update(situacion)
    # El liquidador entra a descargar lo que ya se cerró: el estado de la
    # escuela —personal, documentación, cursos— no es asunto suyo.
    contexto["ve_la_escuela"] = _trabaja_en_la_escuela(request.user, institucion)
    contexto["puede_cubrir"] = request.user.has_perm("licencias.change_cobertura")
    contexto["puesta_en_marcha"] = _puesta_en_marcha(contexto)
    contexto["bienvenida"] = bienvenida_para(request.user, institucion)
    contexto["pendientes"] = pendientes_de(
        institucion,
        request.user,
        situacion=situacion,
        documentos_vencidos=personal["documentos_vencidos"],
    )
    return render(request, "core/inicio.html", contexto)


def _puesta_en_marcha(contexto) -> list[dict]:
    """Los pasos para dejar la escuela lista, con el link a cada alta.

    Estaban como texto: había que saber en qué parte del panel se cargaba cada
    cosa. Con el link, una escuela nueva se arma siguiendo la lista.
    """
    return [
        {
            "texto": "Cargar los niveles que tiene la escuela",
            "hecho": bool(contexto["cantidad_niveles"]),
            "url": reverse("admin:estructura_nivel_add"),
        },
        {
            "texto": "Abrir el ciclo lectivo y sus períodos (cuatrimestres)",
            "hecho": contexto["ciclo"] is not None,
            "url": reverse("admin:estructura_ciclolectivo_add"),
        },
        {
            "texto": "Definir turnos y la grilla de bloques horarios",
            "hecho": contexto["tiene_grilla"],
            "url": reverse("admin:estructura_esquemahorario_add"),
        },
        {
            "texto": "Crear los cursos y divisiones del ciclo",
            "hecho": bool(contexto["cantidad_cursos"]),
            "url": reverse("admin:estructura_curso_add"),
        },
        {
            "texto": "Cargar las materias y el plan de estudios de cada curso",
            "hecho": bool(contexto["cantidad_materias"]),
            "url": reverse("admin:estructura_materiaplan_add"),
        },
    ]


def _trabaja_en_la_escuela(usuario, institucion) -> bool:
    """Quién ve el estado de la escuela y no solo lo suyo."""
    if usuario.is_superuser:
        return True
    return bool(usuario.roles_en(institucion) & {Rol.SECRETARIA, Rol.DIRECTIVO})


def _solo_es_docente(usuario, institucion) -> bool:
    if usuario.is_superuser or usuario.is_staff:
        return False
    return usuario.roles_en(institucion) == {Rol.DOCENTE}


def _situacion_del_dia(institucion) -> dict:
    """Lo que la secretaría necesita ver hoy: licencias, coberturas y clases."""
    from datetime import date

    from asistencia.parte import coberturas_pendientes, parte_diario
    from licencias.models import licencias_vigentes, suplencias_por_vencer

    hoy = date.today()
    parte = parte_diario(institucion, hoy)
    return {
        "licencias_en_curso": licencias_vigentes(institucion, hoy).count(),
        "horas_sin_cobertura": len(parte.sin_cobertura),
        "coberturas_pendientes": len(coberturas_pendientes(institucion, hoy)),
        "suplencias_por_vencer": list(suplencias_por_vencer(institucion)),
        "parte_sin_registrar": parte.sin_registrar if parte.hay_clases else 0,
        "hay_clases_hoy": parte.hay_clases,
    }


def _resumen_de_personal(institucion) -> dict:
    """Personal activo y estado de la documentación (módulo de legajos)."""
    from legajos.models import DocumentoLegajo, EstadoLegajo, FuentePago, Legajo

    activos = Legajo.objects.del_contexto().filter(estado=EstadoLegajo.ACTIVO)

    # Los documentos con vencimiento son pocos (unos cientos): se revisan en
    # Python porque cada tipo tiene su propia ventana de preaviso.
    documentos = (
        DocumentoLegajo.objects.filter(
            legajo__institucion=institucion, fecha_vencimiento__isnull=False
        )
        .select_related("tipo", "legajo")
        .order_by("fecha_vencimiento")
    )
    vencidos = [documento for documento in documentos if documento.esta_vencido]
    por_vencer = [documento for documento in documentos if documento.por_vencer]

    return {
        "cantidad_personal": activos.count(),
        "personal_por_fuente": {
            "subvencionado": activos.filter(
                cargos__fuente_pago=FuentePago.SUBVENCIONADO, cargos__fecha_baja__isnull=True
            )
            .distinct()
            .count(),
            "interno": activos.filter(
                cargos__fuente_pago=FuentePago.INTERNO, cargos__fecha_baja__isnull=True
            )
            .distinct()
            .count(),
        },
        "documentos_vencidos": vencidos,
        "documentos_por_vencer": por_vencer,
    }


@require_POST
@login_required
def cambiar_institucion(request):
    """Cambia la escuela activa, validando que el usuario tenga acceso."""
    institucion_id = request.POST.get("institucion")
    destino = request.POST.get("siguiente") or reverse("inicio")

    elegida = request.user.instituciones().filter(pk=institucion_id).first()
    if elegida is None:
        messages.error(request, "No tenés acceso a esa institución.")
        return HttpResponseRedirect(destino)

    request.session[CLAVE_SESION] = elegida.pk
    messages.success(request, f"Trabajando en {elegida}.")
    return HttpResponseRedirect(destino)


@login_required
def estado_del_sistema(request):
    """Qué versión está corriendo y con qué anda.

    Es la pantalla que se mira antes de reportar un problema: dice la versión,
    la revisión exacta del código y qué dependencias opcionales están
    instaladas, que es de donde salen la mitad de las diferencias entre un
    servidor y otro.

    La ve quien entra al panel de administración —secretaría y directivo—:
    dice con qué base corre y qué direcciones acepta, que no es información
    para el resto.
    """
    if not request.user.is_staff:
        raise PermissionDenied
    return render(request, "core/sistema.html", {"sistema": informacion()})


@login_required
def circuito(request):
    """El dibujo del sistema: qué se apoya en qué, con el link a cada paso.

    Es el modelo mental que hasta ahora solo estaba en el manual y en la
    cabeza de quien lo armó. Puesto en el sistema, alcanza un minuto para
    entender por qué las cosas aparecen solas.
    """
    pasos = [
        {
            "quien": "El docente",
            "que": "Avisa que no viene",
            "url": reverse("portal_inicio"),
            "porque": "Desde el celular, apenas se levanta. Todavía no es una licencia.",
        },
        {
            "quien": "Secretaría",
            "que": "Carga la licencia",
            "url": reverse("admin:licencias_licencia_changelist"),
            "porque": "Con el certificado en la mano, con su artículo y sus fechas.",
        },
        {
            "quien": "Dirección",
            "que": "La aprueba",
            "url": reverse("admin:licencias_licencia_changelist"),
            "porque": "Recién aprobada empieza a tener efecto en todo lo que sigue.",
        },
        {
            "quien": "Secretaría",
            "que": "Decide la cobertura",
            "url": reverse("admin:licencias_cobertura_changelist"),
            "porque": (
                "Suplente designado, o constancia de que el curso queda sin clase. "
                "Una licencia no obliga a cubrir."
            ),
        },
        {
            "quien": "El sistema",
            "que": "Arma el parte y el cuadro de cursos",
            "url": reverse("parte_diario"),
            "porque": (
                "Cruza el horario vigente con las licencias y las coberturas. "
                "Solo queda marcar lo que pasó fuera de lo previsto."
            ),
            "automatico": True,
        },
        {
            "quien": "Secretaría",
            "que": "Compila el mes",
            "url": reverse("novedades_periodos"),
            "porque": (
                "Recorre altas, bajas, licencias, suplencias e inasistencias y "
                "arma las líneas, cada una a su planilla."
            ),
        },
        {
            "quien": "Secretaría",
            "que": "Cierra el mes",
            "url": reverse("novedades_periodos"),
            "porque": "Las novedades quedan congeladas: es la constancia de lo informado.",
        },
        {
            "quien": "Liquidación",
            "que": "Descarga la planilla",
            "url": reverse("novedades_periodos"),
            "porque": "Recién con el mes cerrado. Un borrador todavía puede cambiar.",
        },
    ]
    return render(request, "core/circuito.html", {"pasos": pasos})


@require_POST
@login_required
def ocultar_bienvenida(request):
    """La bienvenida del primer ingreso no vuelve a aparecer."""
    request.user.vio_la_bienvenida = True
    request.user.save(update_fields=["vio_la_bienvenida"])
    return HttpResponseRedirect(request.POST.get("siguiente") or reverse("inicio"))
