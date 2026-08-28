# SGE — Sistema de Gestión para Secretaría Escolar

Aplicación web para secretarías de escuelas de gestión privada (primer caso:
escuela privada subvencionada de San Luis, Argentina). Resuelve la operación
diaria del personal docente:

- **RRHH / Legajos** — cargos con fuente de pago (subvencionado/interno),
  documentación con vencimientos, certificación de servicios.
- **Horarios** — generador automático a partir de las declaraciones juradas y
  restricciones, minimizando los días que cada docente debe asistir.
- **Asistencia** — parte diario autogenerado a partir del horario vigente.
- **Licencias y suplencias** — catálogo por artículo con topes de días;
  cobertura opcional ("sin reemplazo" → alumnos libres).
- **Novedades para liquidación** — compilación mensual separada en Planilla
  Oficial e Interna, con cierre auditable.

📄 **[REQUERIMIENTOS.md](REQUERIMIENTOS.md)** — documento funcional completo:
alcance, módulos, modelo de datos, arquitectura y roadmap por fases.
🚀 **[DESPLIEGUE.md](DESPLIEGUE.md)** — cómo publicarlo (PythonAnywhere o Docker).
🛠️ **[CLAUDE.md](CLAUDE.md)** — convenciones para desarrollar el proyecto.

## Estado

**Fases 0 y 1 implementadas.**

- **F0 · Fundaciones** — instituciones con aislamiento de datos, usuarios y
  roles, auditoría, y la estructura del colegio: niveles, ciclo lectivo y
  períodos, turnos, grilla horaria flexible, cursos y plan de estudios.
- **F1 · RRHH / Legajos** — legajos del personal, cargos con fuente de pago y
  situación de revista, documentación con alertas de vencimiento, títulos,
  servicios anteriores, cómputo de antigüedad y **certificación de servicios
  en PDF**.
- **F2 · Horarios** — declaraciones juradas de disponibilidad, versiones de
  horario por cuatrimestre y **generador automático** que ubica todas las horas
  del plan sin choques, minimizando los días que cada docente debe asistir.
  Grillas por curso y por docente, imprimibles.

- **F3 · Asistencia y licencias** — catálogo de licencias por artículo con sus
  topes, flujo de aprobación, decisión de cobertura (suplente o alumnos libres),
  **parte diario** que se arma solo desde el horario vigente descontando
  licencias y sumando suplentes, y resumen mensual por persona y planilla.

- **F4 · Novedades y cierre mensual** — compilación automática del mes desde
  altas, bajas, licencias, suplencias e inasistencias, **ruteada sola a planilla
  Oficial o Interna** según quién paga cada cargo; revisión por persona con
  checklist de "ya informada", cierre auditable que congela las novedades, y
  exportación a Excel, CSV y PDF con las columnas de la planilla del liquidador.

Próxima fase: **F5 — Portal docente**.

## Poner en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env      # trae SGE_DEBUG=1 y una clave de relleno
python manage.py migrate
python manage.py cargar_demo --password una-clave-segura     # datos de ejemplo
python manage.py runserver
```

Entrar a http://127.0.0.1:8000/ con `secretaria@ejemplo.edu.ar`, y al portal
docente en /portal/ con `docente@ejemplo.edu.ar`.
Para un usuario propio: `python manage.py createsuperuser`.

`cargar_demo` deja la escuela **funcionando**: arma la estructura, genera y
publica el horario, carga licencias con y sin suplente sobre docentes que hoy
tienen clase, registra la asistencia de los últimos días y compila el mes de
novedades. Tarda alrededor de un minuto, casi todo en el generador. Si solo
querés la estructura vacía, `cargar_piloto` hace esa parte y es inmediato.
Cualquiera de los dos se puede volver a correr: no duplican nada.

El `.env` no es opcional: sin él el sistema arranca en modo producción y se
planta pidiendo `SGE_SECRET_KEY`. Es a propósito —un servidor no debe quedar
nunca con la clave de ejemplo—, pero en una PC de desarrollo alcanza con copiar
el archivo tal cual.

En Windows (PowerShell) cambian tres líneas:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

El resto es igual. Requiere Python 3.10 o mayor (Django 5.1); la 3.12 es la que
usa la integración continua. Los PDF salen como página web, porque WeasyPrint
necesita librerías de sistema que en Windows no vienen con `pip`: se imprimen
con Ctrl+P → Guardar como PDF, y el documento es el mismo.

### Con Docker (PostgreSQL incluido)

```bash
cp .env.example .env      # completar SGE_SECRET_KEY
docker compose up --build
```

## Desarrollo

```bash
pytest                    # pruebas
ruff check . && ruff format .
```

Configuración por variables de entorno (ver `.env.example`). Sin
`SGE_DATABASE_URL` usa SQLite; con `postgres://…` usa PostgreSQL.

## Estructura del código

```
config/       configuración de Django (settings, urls, wsgi)
core/         instituciones, usuarios, roles, aislamiento multi-escuela, auditoría
estructura/   niveles, ciclo lectivo, períodos, turnos, grilla horaria, cursos, materias
legajos/      personal, cargos, documentación, títulos, antigüedad, certificaciones
horarios/     DDJJ, versiones de horario, generador con OR-Tools, grillas
licencias/    tipos por artículo, licencias, suplencias y coberturas
asistencia/   parte diario, registros y resumen mensual
novedades/    compilación mensual, cierre del período y exportaciones
templates/    plantillas HTML
static/       hoja de estilos propia (sin build ni CDN)
```
