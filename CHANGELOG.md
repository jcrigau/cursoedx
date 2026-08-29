# Historial de versiones

Qué cambió en cada versión del SGE, en orden inverso. La versión que está
corriendo se ve al pie de cualquier pantalla, y con más detalle en
**Estado del sistema** (o con `python manage.py mostrar_version`).

La numeración acompaña las fases del plan (`REQUERIMIENTOS.md` §7): la minor
sube al terminar cada fase. El **1.0 queda reservado** para cuando el sistema
esté en uso diario en una escuela, con un ciclo lectivo completo encima.

---

## 0.5.0 — Portal docente (F5)

Cada docente entra con su usuario y ve lo suyo, sin pasar por secretaría.

- Horario propio, legajo y licencias en pantalla.
- Aviso de inasistencia desde el celular, que aparece en el parte del día.
- Fichaje con geolocalización, comparado contra la ubicación de la escuela.
  La fichada se guarda siempre, esté dentro del radio o no: la ubicación puede
  fallar por mil motivos y no se le puede negar a nadie la constancia de que
  llegó.
- Aplicación instalable en el teléfono (PWA). La caché guarda solo la
  estructura de las pantallas, nunca los datos: nadie ve un horario viejo.

## 0.4.0 — Novedades y cierre mensual (F4)

- Compilación automática del mes desde altas, bajas, licencias, suplencias e
  inasistencias.
- Ruteo solo a planilla **Oficial** o **Interna** según la fuente de pago del
  cargo que originó cada línea. Una licencia sobre dos cargos de distinta
  fuente genera dos líneas, que es exactamente donde se cometían los errores.
- Recompilar actualiza en vez de duplicar, y no pisa lo cargado a mano ni lo
  congelado por un cierre.
- Cierre auditable con congelado, reapertura con motivo registrado.
- Exportación a Excel, CSV y PDF con las columnas de la planilla del liquidador.

## 0.3.0 — Asistencia y licencias (F3)

- Catálogo de licencias por artículo del régimen de San Luis, con topes.
- Flujo de aprobación y coberturas: suplente designado, o constancia de que el
  curso queda sin clase.
- Parte diario que **no se guarda**: se calcula cruzando el horario vigente con
  licencias y coberturas. Solo se guardan las novedades del día.
- Resumen mensual por persona y por planilla.

## 0.2.0 — Horarios (F2)

- Declaración jurada de disponibilidad por docente.
- Versiones de horario por período, con estados borrador / vigente / histórico.
- Generador con OR-Tools que **minimiza los días de asistencia de cada
  docente**, que es el objetivo que pidió la escuela.
- Asignaciones bloqueables para fijar a mano lo que no se negocia.
- Grillas por curso y por docente, exportables a PDF.

## 0.1.0 — Legajos y RRHH (F1)

- Legajos, cargos con fuente de pago y situación de revista.
- Documentación con vencimientos, títulos y servicios anteriores.
- Cómputo de antigüedad que **une los períodos antes de contarlos**: varios
  cargos simultáneos son un solo tiempo trabajado.
- Certificación de servicios en PDF, distinguiendo titulares de suplentes.

## 0.0.1 — Fundaciones (F0)

- Multi-institución con aislamiento estricto: ninguna consulta cruza escuelas.
- Usuarios, roles y auditoría de las acciones sensibles.
- Estructura del colegio: niveles, ciclo lectivo, períodos, turnos, grilla
  horaria, cursos, materias y plan de estudios.
