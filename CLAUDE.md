# Guía del proyecto para sesiones de Claude Code

Sistema de gestión para secretarías escolares. **`REQUERIMIENTOS.md` es la
fuente de verdad**: alcance, módulos, modelo de datos y roadmap por fases. Si
una decisión cambia, se actualiza ese documento en el mismo commit que el
código.

## Cómo se trabaja

- **Una fase por vez** (F0…F6 en `REQUERIMIENTOS.md` §7). Fase terminada =
  algo usable por la secretaría, con pruebas.
- Todo en **español**: modelos, campos, variables, comentarios, mensajes de la
  interfaz y de error. La secretaría lee lo que el sistema dice.
- Antes de cerrar un cambio: `ruff check . && ruff format . && pytest`.

## Estado

- **F0 (fundaciones): lista.** Multi-institución, usuarios y roles, auditoría,
  y toda la estructura del colegio (niveles, ciclo lectivo, períodos, turnos,
  grilla horaria, cursos, materias y plan de estudios).
- **F1 (RRHH / legajos): lista.** Legajos, cargos con fuente de pago y
  situación de revista, documentación con vencimientos, títulos, servicios
  anteriores, cómputo de antigüedad y certificación de servicios en PDF.
- Siguiente: **F2 (horarios)** — el generador con OR-Tools.

## Comandos

```bash
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py cargar_piloto --password una-clave   # datos de ejemplo
python manage.py sincronizar_permisos                 # tras agregar modelos
python manage.py runserver
pytest
```

Con Docker: `docker compose up --build` (requiere `SGE_SECRET_KEY` en el `.env`).

## Reglas de arquitectura

**Aislamiento entre escuelas — lo más importante.** Una consulta que cruce
instituciones expone datos laborales de otra escuela.

- Todo modelo de negocio hereda de `core.models.ModeloInstitucional`
  (trae `institucion`, `creado_en`, `actualizado_en`).
- En vistas y servicios se consulta con **`Modelo.objects.del_contexto()`**,
  que filtra por la institución activa. `objects.all()` no filtra: se reserva
  para migraciones, comandos y soporte.
- El admin hereda de `core.admin.AdminInstitucional`, que filtra el listado,
  acota los desplegables y asigna la institución al crear.
- Si un modelo llega a la institución por una relación (no tiene el campo
  propio), hay que declararlo con `registrar_ruta_institucion(Modelo,
  "padre__institucion")` — ver `estructura/admin.py`.
- La institución activa vive en `core.tenancy`; fuera de un request se fija con
  `with usar_institucion(inst): ...`.

**Otras convenciones**

- La fuente de pago (subvencionado/interno) es atributo **del cargo**, nunca de
  la persona: de ahí sale sola la separación entre planilla Oficial e Interna.
  Una persona con cargos de las dos fuentes es el caso "mixto", sin ningún
  campo extra.
- Los períodos de servicio **se unen antes de contarse** (`legajos.antiguedad`):
  varios cargos simultáneos son un solo tiempo trabajado.
- Al agregar modelos nuevos hay que sumarlos a `core/permisos.py`, o los roles
  existentes no van a poder administrarlos.
- Las validaciones de coherencia van en `clean()` del modelo, para que las
  aproveche cualquier formulario.
- Las acciones sensibles (cierres, reaperturas, exportaciones) se registran con
  `core.models.registrar_auditoria`.
- La grilla horaria no se asume uniforme: cada día tiene sus bloques y cada
  curso sigue un `EsquemaHorario` (con almuerzo, sin almuerzo…).

## Decisiones tomadas

- **Interfaz**: por ahora el admin de Django más un tablero propio. El CSS es
  propio y self-hosted (`static/css/sge.css`), sin build ni CDN, para que el
  sistema ande con internet intermitente. Si en F1+ crece la interfaz, se
  evalúa Tailwind con pipeline.
- **Autenticación**: Django estándar con login por email. `django-allauth`
  queda para F5 (portal docente), si hace falta autogestión de contraseñas.
- **Tareas pesadas** (generador de horarios, PDFs): sin Redis todavía, para
  poder desplegar gratis. Se migra a django-rq cuando haya hosting pago.
