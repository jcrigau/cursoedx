"""Pantallas de legajos: la planta completa, la búsqueda y la certificación."""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import AccionAuditada, registrar_auditoria
from core.pdf import responder_pdf
from core.texto import contiene
from estructura.models import Materia
from licencias.models import licencias_vigentes

from .antiguedad import antiguedad_en_la_institucion, calcular_antiguedad
from .models import EstadoLegajo, Legajo


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def certificacion_servicios(request, pk):
    """Genera la certificación de servicios de un legajo.

    Sale en PDF; con ``?formato=html`` se ve en pantalla, que es cómodo para
    revisarla antes de imprimirla.
    """
    legajo = get_object_or_404(Legajo.objects.del_contexto().select_related("institucion"), pk=pk)
    a_fecha = date.today()

    cargos = list(legajo.cargos.select_related("materia", "curso", "nivel").order_by("fecha_alta"))
    contexto = {
        "legajo": legajo,
        "institucion": legajo.institucion,
        "cargos": cargos,
        "servicios_anteriores": list(legajo.servicios_anteriores.order_by("desde")),
        "antiguedad_institucion": antiguedad_en_la_institucion(legajo, a_fecha),
        "antiguedad_total": calcular_antiguedad(legajo, a_fecha),
        "fecha": a_fecha,
        "emitido_por": request.user,
    }
    html = render_to_string("legajos/certificacion.html", contexto, request=request)

    if request.GET.get("formato") == "html":
        return HttpResponse(html)

    registrar_auditoria(
        AccionAuditada.EXPORTACION,
        legajo,
        usuario=request.user,
        descripcion=f"Certificación de servicios de {legajo.nombre_completo}",
    )
    return responder_pdf(
        html, request, f"certificacion-servicios-{legajo.apellido}-{legajo.nombre}"
    )


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def buscar(request):
    """Buscar una persona por apellido, nombre o CUIL.

    La secretaría piensa en personas —«¿qué pasa con Herrera?»— y hasta ahora
    para llegar a alguien había que saber en qué pantalla estaba lo que se
    quería ver. Acá se escribe el apellido y sale la persona con todo lo suyo
    a un clic: sus cargos, si está de licencia hoy, y qué documentación debe.
    """
    consulta = request.GET.get("q", "").strip()
    encontrados = []

    if consulta:
        # Se compara sin tildes y sin mayúsculas: nadie escribe «Benítez» con
        # tilde al buscar. La base tiene un legajo por persona —unos cientos
        # como mucho—, así que filtrar en Python cuesta nada y anda igual sobre
        # SQLite, que es con lo que arranca una escuela chica.
        todos = (
            Legajo.objects.del_contexto().prefetch_related("cargos").order_by("apellido", "nombre")
        )
        encontrados = [
            legajo
            for legajo in todos
            if contiene(legajo.apellido, consulta)
            or contiene(legajo.nombre, consulta)
            or contiene(legajo.cuil, consulta)
        ][:25]

    hoy = date.today()
    de_licencia = {
        licencia.legajo_id: licencia for licencia in licencias_vigentes(request.institucion, hoy)
    }
    for legajo in encontrados:
        legajo.licencia_de_hoy = de_licencia.get(legajo.id)

    return render(
        request,
        "legajos/buscar.html",
        {"consulta": consulta, "encontrados": encontrados, "hoy": hoy},
    )


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def personal(request):
    """Todo el personal de la escuela, en una sola pantalla.

    El listado del panel sirve para editar de a uno; esta sirve para mirar la
    planta completa: quién está, cuántas horas tiene, y qué materias puede dar
    —que es lo que después permite encontrarle reemplazo a un curso—.
    """
    consulta = request.GET.get("q", "").strip()
    solo = request.GET.get("solo", "activos")
    materia_id = request.GET.get("materia", "")

    personas = (
        Legajo.objects.del_contexto()
        .prefetch_related("cargos__materia", "materias_que_puede_dar")
        .order_by("apellido", "nombre")
    )
    if solo == "activos":
        personas = personas.filter(estado=EstadoLegajo.ACTIVO)

    personas = list(personas)
    if consulta:
        personas = [
            legajo
            for legajo in personas
            if contiene(legajo.apellido, consulta)
            or contiene(legajo.nombre, consulta)
            or contiene(legajo.cuil, consulta)
        ]

    materias = list(Materia.objects.del_contexto().order_by("nombre"))
    if materia_id.isdigit():
        # La unión de lo que declaró y lo que dicta hoy: el mismo criterio que
        # usa la búsqueda de reemplazos.
        elegida = int(materia_id)
        personas = [
            legajo
            for legajo in personas
            if any(materia.pk == elegida for materia in legajo.materias_que_puede_dar.all())
            or any(
                cargo.materia_id == elegida
                for cargo in legajo.cargos.all()
                if cargo.fecha_baja is None
            )
        ]

    hoy = date.today()
    de_licencia = {licencia.legajo_id for licencia in licencias_vigentes(request.institucion, hoy)}
    for legajo in personas:
        legajo.esta_de_licencia = legajo.id in de_licencia
        legajo.horas = sum(
            cargo.horas_semanales or 0
            for cargo in legajo.cargos.all()
            if cargo.fecha_baja is None or cargo.fecha_baja >= hoy
        )

    return render(
        request,
        "legajos/personal.html",
        {
            "personas": personas,
            "consulta": consulta,
            "solo": solo,
            "materias": materias,
            "materia_elegida": int(materia_id) if materia_id.isdigit() else None,
            "puede_editar": request.user.has_perm("legajos.change_legajo"),
        },
    )


@require_POST
@login_required
@permission_required("legajos.change_legajo", raise_exception=True)
def guardar_materias(request, pk: int):
    """Guarda las materias que una persona puede dar."""
    legajo = get_object_or_404(Legajo.objects.del_contexto(), pk=pk)
    elegidas = Materia.objects.del_contexto().filter(pk__in=request.POST.getlist("materias"))
    legajo.materias_que_puede_dar.set(elegidas)

    messages.success(
        request,
        f"{legajo.nombre_completo}: {elegidas.count()} materia"
        f"{'s' if elegidas.count() != 1 else ''} habilitada"
        f"{'s' if elegidas.count() != 1 else ''}.",
    )
    return HttpResponseRedirect(request.POST.get("siguiente") or reverse("personal"))


@login_required
@permission_required("legajos.change_legajo", raise_exception=True)
def materias_de(request, pk: int):
    """Las materias que puede dar una persona, para tildar."""
    legajo = get_object_or_404(
        Legajo.objects.del_contexto().prefetch_related("materias_que_puede_dar"), pk=pk
    )
    ya_dio = {cargo.materia_id for cargo in legajo.cargos.all() if cargo.materia_id is not None}
    puede = set(legajo.materias_que_puede_dar.values_list("pk", flat=True))

    materias = []
    for materia in Materia.objects.del_contexto().select_related("nivel").order_by("nombre"):
        materia.tildada = materia.pk in puede
        materia.ya_la_dio = materia.pk in ya_dio
        materias.append(materia)

    return render(
        request,
        "legajos/materias.html",
        {"legajo": legajo, "materias": materias},
    )


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def ficha(request, pk: int):
    """La persona completa, para leer.

    El formulario del panel es para cargar; esta pantalla es para responder
    «¿qué pasa con Herrera?» sin editar nada: sus datos, sus cargos, su año
    —licencias, ausencias, suplencias que hizo— y su antigüedad, con los
    botones de lo que se hace con una persona: certificar, habilitar materias,
    editar.
    """
    legajo = get_object_or_404(
        Legajo.objects.del_contexto().prefetch_related(
            "cargos__materia", "cargos__curso", "materias_que_puede_dar", "documentos__tipo"
        ),
        pk=pk,
    )
    hoy = date.today()
    inicio_del_anio = hoy.replace(month=1, day=1)

    licencias = list(
        legajo.licencias.filter(fecha_fin__gte=inicio_del_anio)
        .select_related("tipo")
        .order_by("-fecha_inicio")
    )
    ausencias = list(
        legajo.asistencias.filter(fecha__gte=inicio_del_anio)
        .select_related("licencia")
        .order_by("-fecha")
    )
    suplencias_hechas = list(
        legajo.suplencias.filter(fecha_fin__gte=inicio_del_anio)
        .select_related("cargo__legajo", "cargo__materia", "cargo__curso")
        .order_by("-fecha_inicio")
    )
    licencia_de_hoy = next(
        (
            licencia
            for licencia in licencias
            if licencia.estado == "APROBADA" and licencia.fecha_inicio <= hoy <= licencia.fecha_fin
        ),
        None,
    )

    return render(
        request,
        "legajos/ficha.html",
        {
            "legajo": legajo,
            "hoy": hoy,
            "licencia_de_hoy": licencia_de_hoy,
            "cargos_vigentes": list(legajo.cargos_vigentes()),
            "licencias": licencias,
            "ausencias": ausencias,
            "suplencias_hechas": suplencias_hechas,
            "antiguedad_total": calcular_antiguedad(legajo),
            "antiguedad_aca": antiguedad_en_la_institucion(legajo),
            "documentos": list(legajo.documentos.all()),
            "puede_editar": request.user.has_perm("legajos.change_legajo"),
        },
    )


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def exportar_personal(request):
    """Descarga la planta en Excel, lista para corregir y volver a subir."""
    from io import BytesIO

    from . import planilla

    libro = planilla.exportar(request.institucion)
    contenido = BytesIO()
    libro.save(contenido)

    registrar_auditoria(
        AccionAuditada.EXPORTACION,
        institucion=request.institucion,
        usuario=request.user,
        modelo="Legajo",
        descripcion="Exportó la planilla del personal",
    )
    respuesta = HttpResponse(
        contenido.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta["Content-Disposition"] = 'attachment; filename="personal.xlsx"'
    return respuesta


@login_required
@permission_required("legajos.add_legajo", raise_exception=True)
def importar_personal(request):
    """Sube la planilla corregida: actualiza, crea, y observa lo dudoso."""
    from . import planilla

    resultado = None
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if archivo is None:
            messages.error(request, "Elegí el archivo .xlsx que descargaste de acá.")
        else:
            resultado = planilla.importar(request.institucion, archivo)
            registrar_auditoria(
                AccionAuditada.MODIFICACION,
                institucion=request.institucion,
                usuario=request.user,
                modelo="Legajo",
                descripcion=(
                    f"Importó la planilla del personal: {resultado.creados} altas, "
                    f"{resultado.actualizados} actualizados"
                ),
            )
            if resultado.total:
                messages.success(
                    request,
                    f"Listo: {resultado.creados} persona{'s' if resultado.creados != 1 else ''} "
                    f"nueva{'s' if resultado.creados != 1 else ''} y "
                    f"{resultado.actualizados} actualizada"
                    f"{'s' if resultado.actualizados != 1 else ''}.",
                )

    return render(request, "legajos/importar.html", {"resultado": resultado})
