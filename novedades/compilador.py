"""Compilación de las novedades del mes.

Recorre lo que el sistema ya registró —cargos, licencias, asistencia— y arma
las líneas del informe. Se puede volver a compilar cuantas veces haga falta:
cada novedad automática lleva una *clave de origen* que identifica el hecho que
la generó, así una segunda compilación actualiza en lugar de duplicar, y no
pierde lo que la secretaría ya marcó como informado.

Nunca toca las novedades cargadas a mano ni las congeladas por un cierre.

Sobre el destino: cada línea va a la planilla del **cargo** que la origina, no
de la persona. Por eso una licencia que afecta dos cargos de distinta fuente
genera dos líneas, una a cada planilla — que es exactamente el caso "mixto"
donde hoy se cometen los errores.
"""

from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.utils import timezone

from asistencia.models import EstadoAsistencia, RegistroAsistencia
from asistencia.reportes import dias_en_el_mes, limites_del_mes
from legajos.models import Cargo, MotivoBaja
from licencias.models import Cobertura, EstadoLicencia, Licencia, TipoCobertura

from .models import Destino, Novedad, Origen, TipoNovedad

SIN_REEMPLAZO = "SIN REEMPLAZO"


@dataclass
class Resultado:
    creadas: int = 0
    actualizadas: int = 0
    avisos: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.creadas + self.actualizadas


def compilar(periodo, usuario=None) -> Resultado:
    """Arma o actualiza las novedades automáticas del período."""
    resultado = Resultado()
    if periodo.esta_cerrado:
        resultado.avisos.append(
            "El período está cerrado: hay que reabrirlo para volver a compilar."
        )
        return resultado

    inicio, fin = limites_del_mes(periodo.anio, periodo.mes)

    with transaction.atomic():
        _altas_y_bajas(periodo, inicio, fin, resultado)
        _licencias(periodo, inicio, fin, resultado)
        _inasistencias(periodo, inicio, fin, resultado)
        _tardanzas(periodo, inicio, fin, resultado)

        periodo.compilado_en = timezone.now()
        periodo.save(update_fields=["compilado_en", "actualizado_en"])

    return resultado


# -- cada fuente de novedades ------------------------------------------------


def _altas_y_bajas(periodo, inicio: date, fin: date, resultado: Resultado):
    """Designaciones que empiezan o terminan en el mes, suplencias incluidas."""
    institucion = periodo.institucion

    for cargo in Cargo.objects.filter(
        institucion=institucion, fecha_alta__gte=inicio, fecha_alta__lte=fin
    ).select_related("legajo", "materia", "curso", "nivel"):
        _guardar(
            periodo,
            resultado,
            clave=f"cargo_alta:{cargo.id}",
            legajo=cargo.legajo,
            cargo=cargo,
            tipo=TipoNovedad.ALTA,
            fecha=cargo.fecha_alta,
            fecha_fin=cargo.fecha_baja,
            horas=cargo.horas_semanales,
            espacio=_espacio_de(cargo),
            motivo="Alta",
            jornada_completa=cargo.jornada_completa,
            tiempo_determinado=cargo.fecha_baja is not None,
            observaciones=_datos_del_alta(cargo),
        )

    for cargo in (
        Cargo.objects.filter(institucion=institucion, fecha_baja__gte=inicio, fecha_baja__lte=fin)
        .exclude(fecha_baja=None)
        .select_related("legajo", "materia", "curso", "nivel")
    ):
        es_renuncia = cargo.motivo_baja == MotivoBaja.RENUNCIA
        _guardar(
            periodo,
            resultado,
            clave=f"cargo_baja:{cargo.id}",
            legajo=cargo.legajo,
            cargo=cargo,
            tipo=TipoNovedad.RENUNCIA if es_renuncia else TipoNovedad.CESE,
            fecha=cargo.fecha_baja,
            horas=cargo.horas_semanales,
            espacio=_espacio_de(cargo),
            motivo=cargo.get_motivo_baja_display() if cargo.motivo_baja else "Cese",
            jornada_completa=cargo.jornada_completa,
        )


def _licencias(periodo, inicio: date, fin: date, resultado: Resultado):
    """Una línea por cada cargo afectado: cada uno puede ir a otra planilla."""
    licencias = (
        Licencia.objects.filter(
            institucion=periodo.institucion,
            estado=EstadoLicencia.APROBADA,
            fecha_inicio__lte=fin,
            fecha_fin__gte=inicio,
        )
        .select_related("legajo", "tipo")
        .prefetch_related("coberturas__suplente", "cargos")
    )

    for licencia in licencias:
        dias = dias_en_el_mes(licencia.fecha_inicio, licencia.fecha_fin, periodo.anio, periodo.mes)
        if not dias:
            continue

        cargos = list(licencia.cargos_afectados())
        if not cargos:
            resultado.avisos.append(
                f"{licencia.legajo.nombre_completo} tiene una licencia sin cargos vigentes: "
                "no se puede saber a qué planilla informarla."
            )
            continue

        for cargo in cargos:
            _guardar(
                periodo,
                resultado,
                clave=f"licencia:{licencia.id}:cargo:{cargo.id}",
                legajo=licencia.legajo,
                cargo=cargo,
                tipo=TipoNovedad.LICENCIA,
                fecha=max(licencia.fecha_inicio, inicio),
                fecha_fin=licencia.fecha_fin,
                dias=dias,
                horas=cargo.horas_semanales,
                espacio=_espacio_de(cargo),
                motivo=str(licencia.tipo),
                reemplazante=_reemplazante(licencia, cargo),
                presenta_certificado=bool(licencia.certificado),
                jornada_completa=cargo.jornada_completa,
                # Regla del liquidador: solo se informa lo que genera descuento
                # o pago adicional. Una licencia con goce no descuenta.
                impacta_haberes=licencia.tipo.impacta_haberes,
                observaciones=licencia.observaciones,
            )


def _inasistencias(periodo, inicio: date, fin: date, resultado: Resultado):
    """Faltas sin licencia que las respalde: son las que se descuentan."""
    registros = (
        RegistroAsistencia.objects.filter(
            institucion=periodo.institucion,
            fecha__gte=inicio,
            fecha__lte=fin,
            estado__in=[EstadoAsistencia.AUSENTE, EstadoAsistencia.PARCIAL],
            licencia__isnull=True,
        )
        .select_related("legajo")
        .order_by("fecha")
    )

    for registro in registros:
        cargos = list(registro.legajo.cargos_vigentes(registro.fecha))
        if not cargos:
            resultado.avisos.append(
                f"{registro.legajo.nombre_completo} tiene una inasistencia el "
                f"{registro.fecha:%d/%m} pero no tiene cargos vigentes."
            )
            continue

        for cargo in cargos:
            _guardar(
                periodo,
                resultado,
                clave=f"inasistencia:{registro.id}:cargo:{cargo.id}",
                legajo=registro.legajo,
                cargo=cargo,
                tipo=TipoNovedad.INASISTENCIA,
                fecha=registro.fecha,
                dias=1 if registro.estado == EstadoAsistencia.AUSENTE else None,
                horas=registro.horas_afectadas or cargo.horas_semanales,
                espacio=_espacio_de(cargo),
                motivo=registro.get_estado_display(),
                jornada_completa=cargo.jornada_completa,
                observaciones=registro.observaciones,
            )


def _tardanzas(periodo, inicio: date, fin: date, resultado: Resultado):
    """Se informan agrupadas: una línea por persona y planilla, con la cantidad."""
    registros = RegistroAsistencia.objects.filter(
        institucion=periodo.institucion,
        fecha__gte=inicio,
        fecha__lte=fin,
        estado=EstadoAsistencia.TARDE,
    ).select_related("legajo")

    conteo: dict[tuple[int, str], list] = {}
    legajos: dict[int, object] = {}
    for registro in registros:
        legajos[registro.legajo_id] = registro.legajo
        for cargo in registro.legajo.cargos_vigentes(registro.fecha):
            conteo.setdefault((registro.legajo_id, cargo.fuente_pago), []).append(registro)

    for (legajo_id, fuente), lista in conteo.items():
        legajo = legajos[legajo_id]
        cantidad = len(lista)
        _guardar(
            periodo,
            resultado,
            clave=f"tardanzas:{legajo_id}:{fuente}",
            legajo=legajo,
            cargo=None,
            destino=Destino.desde_fuente(fuente),
            tipo=TipoNovedad.TARDANZA,
            fecha=min(registro.fecha for registro in lista),
            dias=cantidad,
            motivo=f"{cantidad} llegada{'s' if cantidad != 1 else ''} tarde en el mes",
        )


# -- utilidades --------------------------------------------------------------


def _espacio_de(cargo) -> str:
    """Lo que la planilla llama "espacio curricular": la materia o el cargo."""
    if cargo.materia_id:
        return cargo.materia.nombre
    return cargo.denominacion


def _datos_del_alta(cargo) -> str:
    """Los datos que el liquidador pide al dar de alta a alguien.

    Hoy se tipean a mano en observaciones; acá salen del legajo.
    """
    from legajos.antiguedad import calcular_antiguedad

    legajo = cargo.legajo
    partes = [f"CUIL: {legajo.cuil}"]
    if legajo.obra_social:
        partes.append(f"Obra social: {legajo.obra_social}")
    antiguedad = calcular_antiguedad(legajo, cargo.fecha_alta)
    partes.append(f"Antigüedad docente: {antiguedad}")
    partes.append(f"Situación de revista: {cargo.get_situacion_revista_display()}")
    if cargo.curso_id:
        partes.append(f"Curso: {cargo.curso}")
    if cargo.observaciones:
        partes.append(cargo.observaciones)
    return " · ".join(partes)


def _reemplazante(licencia, cargo) -> str:
    """Quién cubre ese cargo, o la constancia de que no lo cubre nadie."""
    cobertura = next(
        (item for item in licencia.coberturas.all() if item.cargo_id == cargo.id),
        None,
    )
    if cobertura is None:
        return ""
    if cobertura.tipo == TipoCobertura.SIN_COBERTURA:
        return SIN_REEMPLAZO
    return cobertura.suplente.nombre_completo if cobertura.suplente_id else ""


def _guardar(periodo, resultado: Resultado, *, clave: str, legajo, cargo, tipo, **datos):
    """Crea o actualiza la novedad de ese hecho, sin pisar lo ya informado."""
    destino = datos.pop("destino", None)
    if destino is None:
        destino = Destino.desde_fuente(cargo.fuente_pago) if cargo else Destino.OFICIAL

    valores = {
        "institucion": periodo.institucion,
        "legajo": legajo,
        "cargo": cargo,
        "tipo": tipo,
        "destino": destino,
        "origen": Origen.AUTOMATICA,
        **datos,
    }

    existente = Novedad.objects.filter(periodo=periodo, clave_origen=clave).first()
    if existente is None:
        Novedad.objects.create(periodo=periodo, clave_origen=clave, **valores)
        resultado.creadas += 1
        return

    if existente.congelada or existente.origen == Origen.MANUAL:
        return

    for campo, valor in valores.items():
        setattr(existente, campo, valor)
    existente.save()
    resultado.actualizadas += 1


def coberturas_del_mes(periodo):
    """Suplencias vigentes en el mes: útil para revisar antes de cerrar."""
    inicio, fin = limites_del_mes(periodo.anio, periodo.mes)
    return Cobertura.objects.filter(
        institucion=periodo.institucion,
        tipo=TipoCobertura.SUPLENTE,
        fecha_inicio__lte=fin,
        fecha_fin__gte=inicio,
    ).select_related("suplente", "cargo__legajo", "licencia")
