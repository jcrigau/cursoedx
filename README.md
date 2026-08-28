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
🛠️ **[CLAUDE.md](CLAUDE.md)** — convenciones para desarrollar el proyecto.

## Estado

**Fase 0 (fundaciones) implementada.** Ya se puede cargar la estructura del
colegio: instituciones, usuarios y roles, niveles, ciclo lectivo y períodos,
turnos, grilla horaria flexible, cursos y plan de estudios.

Próxima fase: **F1 — RRHH / legajos**.

## Poner en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python manage.py migrate
python manage.py cargar_piloto --password una-clave-segura   # datos de ejemplo
python manage.py runserver
```

Entrar a http://127.0.0.1:8000/ con `secretaria@ejemplo.edu.ar`.
Para un usuario propio: `python manage.py createsuperuser`.

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
templates/    plantillas HTML
static/       hoja de estilos propia (sin build ni CDN)
```
