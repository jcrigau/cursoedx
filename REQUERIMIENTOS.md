# SGE — Sistema de Gestión para Secretaría Escolar

> **Documento de requerimientos** · Versión 1.0 · Agosto 2026
> Nombre comercial: a definir (SGE es nombre de trabajo).
> Este es un documento vivo: se actualiza a medida que se toman decisiones. Sirve como fuente de verdad para las sesiones de desarrollo con Claude Code.

---

## 1. Visión del producto

Aplicación web para la **secretaría de escuelas de gestión privada** que resuelve la operación diaria del personal docente: legajos (RRHH), horarios, asistencia, licencias, suplencias y la **generación de las novedades mensuales para la liquidación de sueldos**.

- **Primer cliente y caso de validación:** la institución donde trabaja el autor — escuela privada **subvencionada** de la provincia de **San Luis** (Argentina), con niveles inicial, primaria y secundaria.
- **Ambición comercial:** producto **SaaS multi-institución**, para ofrecer a otras escuelas. Toda decisión de diseño debe evitar hardcodear la realidad de una sola escuela: lo específico (régimen de licencias, formatos de planillas, estructura horaria) se resuelve por **configuración por institución**.
- **Estrategia de alcance:** la versión 1 se enfoca en el **nivel secundario** (el más complejo por las horas cátedra), pero el modelo de datos contempla desde el inicio los tres niveles para incorporarlos después sin rediseño.

### 1.1 Qué NO hace (fuera de alcance)

- **No liquida sueldos.** Calcula y compila *novedades*; la liquidación la hace el estado (personal subvencionado) o el contador de la escuela (personal interno).
- No gestiona alumnos en lo académico (notas, boletines, legajos de alumnos), ni comunicación con familias, ni facturación de cuotas, ni inventario. Los cursos/divisiones existen solo como estructura para los horarios.

---

## 2. Contexto del dominio

### 2.1 La escuela privada subvencionada

En una escuela privada subvencionada conviven **tres situaciones de pago**:

| Tipo de personal | Quién paga el sueldo | A quién se informan las novedades |
|---|---|---|
| **Subvencionado** | El estado provincial (aporte estatal) | Contralor / planilla al organismo de educación de gestión privada de la provincia |
| **Interno** | La escuela | Contador / liquidador de la institución |
| **Mixto** | Una misma persona tiene cargos u horas de ambos orígenes | Cada cargo se informa a su destino correspondiente |

**Regla de modelado central:** la fuente de pago **no es un atributo de la persona sino de cada cargo/hora**. El caso "mixto" emerge naturalmente cuando una persona tiene cargos con distintas fuentes. Toda novedad hereda la fuente de pago del cargo que la origina y se enruta al destino correcto.

### 2.2 Circuito actual de novedades (a reemplazar/asistir)

Hoy la secretaría carga cada novedad **manualmente en un Google Sheet compartido del liquidador, a través de un link de Google Forms** (formulario "Novedades Sueldos"). El formulario real fue relevado y está documentado en el **Anexo A**: campos exactos, valores observados y volumetría (~40 novedades/mes). El sistema debe:

1. **v1:** compilar las novedades del mes y presentarlas listas para trasladar a ese circuito (export con las mismas columnas del Anexo A, checklist de "informada").
2. **v2:** automatizar el traslado (links de Google Forms pre-llenados por novedad y/o escritura directa en el Sheet vía API).

**Regla vigente del liquidador:** solo se informan las novedades que **generan descuento o pago adicional** (antes se cargaban datos de más y se dejó de hacer). El sistema registra todo, pero el paquete a informar filtra por impacto en haberes.

### 2.3 Glosario

| Término | Significado |
|---|---|
| **Legajo** | Carpeta administrativa de un empleado en la institución: datos, cargos, documentación, historial. |
| **Cargo** | Puesto que ocupa una persona: un cargo de base (p. ej. maestro de grado, preceptor) o un paquete de **horas cátedra** (materia + curso). |
| **Hora cátedra** | Unidad de designación en secundaria: se designa por cantidad de horas semanales en una materia y curso. |
| **Situación de revista** | Condición del cargo: **titular**, **provisional/interino** o **suplente**. |
| **Fuente de pago** | Origen del sueldo del cargo: **subvencionado** (estado) o **interno** (escuela). |
| **POF** | Planta Orgánica Funcional: cargos y horas aprobados/financiados por el estado para la escuela. |
| **DDJJ (declaración jurada) de horarios** | Declaración del docente de sus horarios ocupados en otras instituciones y disponibilidad; insumo para armar horarios y controlar incompatibilidades. |
| **Novedad** | Todo hecho del mes que afecta la liquidación: alta, baja/cese, licencia, inasistencia, llegada tarde, suplencia, cambio de situación de revista o de horas. |
| **Contralor** | Rendición/informe periódico al organismo estatal que financia los cargos subvencionados. |
| **Parte diario** | Registro de asistencia del personal de un día. |
| **Alumnos libres** | Horas sin docente ni suplente asignado: el curso queda sin clase. |

---

## 3. Usuarios y roles

| Rol | Permisos principales |
|---|---|
| **Secretaría** | Operación completa: legajos, cargos, horarios, asistencia, licencias, suplencias, novedades, cierres. Es el usuario principal del sistema. |
| **Equipo directivo** | Consulta de todo, tableros e indicadores, aprobación de licencias, firma de certificaciones. |
| **Docente** (fase portal) | Autoservicio: ver su horario, su legajo y documentación, avisar inasistencias, solicitar licencias con adjuntos, fichar (objetivo). |
| **Contador / liquidador** | Solo lectura del paquete de novedades de períodos cerrados; descarga de exports. |
| **Admin del producto** (interno) | Alta y configuración de instituciones (multi-tenant), soporte. |

Los roles se asignan **por institución** (una misma persona podría ser docente en una escuela y directivo en otra).

---

## 4. Módulos funcionales

### M1 · RRHH / Legajos

**Objetivo:** legajo digital completo de cada empleado, con alertas de vencimientos y generación de certificaciones.

**Funciones:**

- ABM de personas y legajos: datos personales (CUIL, DNI, contacto, domicilio), foto, estado (activo/baja).
- **Cargos** por legajo, cada uno con: tipo (cargo de base / horas cátedra), nivel, materia y curso (si aplica), cantidad de horas semanales, **situación de revista** (titular / provisional / suplente), **fuente de pago** (subvencionado / interno), referencia a POF si es subvencionado, fecha de alta y de baja/cese, norma o resolución de designación.
- **Documentación con vencimientos:** apto psicofísico, certificado de antecedentes penales, títulos registrados, etc. Cada documento: tipo, archivo adjunto, fecha de emisión y de vencimiento. **Alertas configurables** (p. ej. 30/60 días antes de vencer).
- **Títulos y formación:** títulos, postítulos y cursos, con puntaje/incumbencias como texto libre en v1.
- **Historial de servicios:** todos los períodos trabajados en la institución (por cargo, con situación de revista) + carga manual de **servicios anteriores en otras instituciones** para el cómputo de **antigüedad docente** (el porcentaje lo aplica quien liquida; el sistema informa años/meses/días).
- **Certificación de servicios (PDF):** documento generado por persona que lista todos los períodos de servicio con cargo, horas, **situación de revista (titular/suplente) visible por período**, desde/hasta, con membrete de la institución y espacio de firma del directivo. Requisito explícito del cliente.

**Historias de usuario:**

- Como secretaria, cargo un docente nuevo con sus horas (12 hs de Matemática en 2°A y 2°B, subvencionadas, provisional) en menos de 5 minutos.
- Como secretaria, veo en el tablero qué documentación vence este mes y a quién reclamársela.
- Como secretaria, genero la certificación de servicios de un docente que la pide para la junta o ANSES, sin armarla a mano en Word.

### M2 · Horarios (secundaria primero)

**Objetivo:** armar y mantener los horarios del colegio; **generarlos automáticamente** a partir de las DDJJ y restricciones. Es la funcionalidad diferencial del producto.

**Estructura previa (configuración por institución):**

- Ciclo lectivo (año), dividido en **cuatrimestres** (algunas materias cambian cuatrimestralmente).
- Turnos (mañana/tarde/…), grilla de **bloques horarios** por turno (cantidad de horas cátedra por día, horarios de inicio/fin, recreos). Duración de la hora cátedra configurable.
- Cursos/divisiones por nivel y turno (p. ej. 3°A TM).
- **Plan de estudios por curso:** materias con carga horaria semanal y vigencia (anual / 1er cuatrimestre / 2do cuatrimestre).
- Asignación docente ↔ materia ↔ curso (derivada de los cargos del M1).
- Recursos compartidos opcionales (canchas, laboratorios) para restricciones.

**DDJJ y restricciones (insumos del generador):**

- Por docente y cuatrimestre: **bloques no disponibles** (horarios en otras escuelas, según su DDJJ) y preferencias.
- Restricciones institucionales configurables: materia fijada a ciertos bloques, máximo de horas seguidas de una misma materia, materias que no pueden compartir recurso (p. ej. dos cursos en la cancha), etc.
- Alerta de DDJJ faltantes antes de generar.

**Generador automático (motor de optimización):**

- *Restricciones duras (obligatorias):* cada curso recibe todas las horas de su plan con el docente designado; un docente no está en dos cursos en el mismo bloque; un curso no tiene dos materias en el mismo bloque; se respetan las DDJJ y las restricciones institucionales.
- *Objetivos blandos (ponderados, configurables):*
  1. **Minimizar la cantidad de días que cada docente debe asistir** (compactar sus horas en pocos días) — prioridad n° 1 pedida por el cliente.
  2. Minimizar "huecos" (horas libres intermedias) de los docentes.
  3. Distribuir una misma materia en días distintos (criterio pedagógico).
  4. Respetar preferencias declaradas.
- El resultado es un **borrador editable**: la secretaría ajusta a mano con **validación en vivo de choques**, puede **bloquear** lo que está bien y **regenerar solo el resto**.
- Corre como tarea en segundo plano con barra de progreso (puede tardar minutos).

**Vigencia y versiones:**

- Cada horario tiene estado (borrador / vigente / histórico) y **vigencia desde/hasta**; el cambio de cuatrimestre publica una nueva versión sin perder la anterior.
- El parte diario y los reportes siempre usan el horario vigente a la fecha.

**Vistas e impresión:**

- Grilla por curso, grilla por docente, horas sin cubrir, disponibilidad de recursos.
- Export a PDF imprimible para carteleras y a Excel.

**Historias de usuario:**

- Como secretaria, cargo las DDJJ de los profesores, aprieto "Generar" y obtengo un horario sin choques donde cada profesor viene la menor cantidad de días posible.
- Como secretaria, al empezar el 2° cuatrimestre publico el horario nuevo (cambian dos materias) y el anterior queda archivado.
- Como directivo, imprimo el horario de cada curso para la cartelera.

### M3 · Asistencia docente

**Objetivo:** registrar la asistencia diaria del personal contra lo que *debería* pasar según el horario vigente.

**Funciones:**

- **Parte diario autogenerado:** para cada fecha, el sistema arma la lista de quién debe estar, en qué bloques, en qué curso — a partir del horario vigente, descontando titulares con licencia y agregando suplentes activos.
- **Carga por secretaría (v1, circuito actual):** desde el libro de firmas/parte en papel, la secretaría marca por docente y día: presente / ausente / llegada tarde / retiro anticipado / **ausencia parcial** (faltó a algunas horas), indicando las horas afectadas.
- Justificación: una ausencia se vincula a una **licencia** (justificada) o queda **injustificada** (impacta en novedades).
- **Aviso previo del docente (fase portal):** el docente notifica desde la app que faltará, con motivo; secretaría confirma y clasifica.
- **Fichaje por app (objetivo, fase portal):** el docente marca presente desde su celular al llegar, con controles (ventana horaria y geolocalización dentro de la escuela).
- Reportes: inasistencias del mes por docente, por cargo y **por fuente de pago**; ranking de ausentismo; llegadas tarde acumuladas.

**Historias de usuario:**

- Como secretaria, cada mañana abro el parte del día ya armado y solo marco los que faltaron.
- Como secretaria, al fin de mes veo cuántos días faltó cada docente en cada cargo, separado por lo subvencionado y lo interno.

### M4 · Licencias

**Objetivo:** gestionar el ciclo completo de licencias con un catálogo configurable por institución/jurisdicción.

**Funciones:**

- **Catálogo de tipos de licencia** configurable: código, denominación, referencia normativa (artículo/inciso del régimen de San Luis en el primer cliente), con/sin goce de haberes, **si impacta en haberes** (descuento/pago adicional), tope de días por año/por caso, si requiere certificado, si es de corto o largo tratamiento.
- **Precarga del catálogo con los motivos reales en uso** (relevados del circuito actual, ver Anexo A.3): Enfermedad, Atención Familiar, Razones Particulares, Congresos/Cursos/Jornadas, Estudios/Investigación, Examen, Fallecimiento Familiar, Maternidad (ref. Art. 83), Matrimonio (12 días), Licencia Especial sin Goce de Haberes, Licencia por Cargo de Mayor Jerarquía. Faltan confirmar artículos, topes y goce por tipo (§8).
- Solicitud de licencia: por secretaría (v1) o por el docente desde el portal (fase 2), sobre uno o más cargos del legajo, con período desde/hasta, adjuntos (certificados médicos) y observaciones.
- Flujo de estados: solicitada → aprobada/rechazada (directivo) → en curso → finalizada; prórrogas/extensiones encadenadas.
- Control automático de **topes** por tipo y año, con aviso al cargar.
- Impacto automático: los días de licencia justifican las ausencias del período y generan la **novedad** correspondiente (con o sin goce).

### M5 · Suplencias

**Objetivo:** cubrir (o decidir no cubrir) las horas de un docente con licencia, y generar las novedades de alta y cese del suplente.

**Reglas del cliente:** las licencias **largas generalmente se cubren**; algunas por día también; otras **no se cubren y los alumnos quedan libres**. Por lo tanto la cobertura es **opcional y por decisión de la escuela**, nunca automática.

**Funciones:**

- Desde una licencia aprobada, decidir por cada cargo/hora afectada: **designar suplente** o **marcar "sin cobertura"** (alumnos libres, visible en el parte diario y en reportes).
- Designación de suplente: persona existente o alta express de una nueva (mini-legajo a completar después); período desde/hasta (puede ser menor a la licencia), horas que cubre.
- El suplente **hereda el horario** de las horas cubiertas: aparece en el parte diario y en las grillas mientras dure la suplencia.
- Novedades automáticas: **alta de suplente** al inicio y **cese** al fin (o al reincorporarse el titular), con días/horas trabajados, enrutadas según la fuente de pago del cargo cubierto.
- Alertas de suplencias por vencer (preaviso de cese).

### M6 · Novedades y cierre mensual

**Objetivo:** compilar automáticamente todas las novedades del período y entregarlas separadas por destino, con un cierre auditable. Es el módulo que le ahorra más tiempo a la secretaría.

**Tipos de novedad (mínimo v1):**

| Novedad | Origen |
|---|---|
| Alta de cargo / aumento de horas | M1 (cargos) |
| Baja: renuncia / cese / reducción de horas | M1 (cargos) |
| Cambio (situación de revista, horas, cargo) | M1 (cargos) |
| Licencia con goce / sin goce (días) | M4 |
| Inasistencia injustificada (días/horas) | M3 |
| Llegadas tarde (cantidad) | M3 |
| Alta de suplente / cese de suplente (días trabajados) | M5 |
| Novedad manual (texto libre + importe/días) | Carga directa |

> Coinciden con los tipos que ya usa el circuito real (Anexo A.2): *Licencia, Alta, Cese, Renuncia, Cambio*. Cada tipo lleva el flag **impacta haberes**: por defecto el paquete a informar incluye solo las novedades que generan descuento o pago adicional; el resto queda como registro interno.

**Funciones:**

- **Compilación automática** del período (mes/año): el sistema recorre cargos, licencias, asistencia y suplencias y arma el listado de novedades por persona y cargo.
- **Separación por destino** según fuente de pago del cargo, con la terminología del circuito real: **"Planilla Oficial"** (cargos subvencionados → contralor estatal) y **"Planilla Interna"** (cargos internos → liquidación de la escuela). El personal mixto aparece en ambas, cada cargo en la suya. En el relevamiento: ~88% Oficial, ~12% Interna.
- **Pre-cierre:** pantalla de revisión con checklist; la secretaría corrige/agrega novedades manuales antes de cerrar.
- **Cierre del período:** congela las novedades (inmutables), registra quién y cuándo cerró; reapertura solo con permiso de directivo y quedando auditado.
- **Salidas v1:**
  - Export **Excel/CSV con mapeo de columnas configurable** para calzar exactamente con el Google Sheet del liquidador (copy-paste directo; columnas relevadas en Anexo A.2).
  - **PDF** resumen del período para firmar/archivar/elevar.
  - Checklist de carga: marcar cada novedad como **"informada"** (con fecha y usuario) para no perder el hilo del circuito manual actual.
  - Acceso del **contador** (rol solo lectura) para descargar el paquete de períodos cerrados.
- **Salidas v2 (automatización del circuito actual):**
  - Generación de **links de Google Forms pre-llenados** por novedad (template de URL con IDs de campos configurable): un click por novedad en lugar de tipear todo.
  - Escritura directa al Google Sheet vía API (cuando el liquidador lo permita).
  - Réplica de la **planilla oficial de contralor de San Luis** (pendiente: conseguir un modelo real, ver §8).

### M7 · Tablero y alertas

- Tablero de secretaría/directivo: ausentismo del mes, licencias en curso, horas sin cobertura hoy (alumnos libres), documentación por vencer, suplencias por vencer, DDJJ faltantes, novedades pendientes de informar.
- Notificaciones: en la app v1; por email en fase 2.

---

## 5. Modelo de datos (borrador)

Todas las tablas de negocio llevan `institucion_id` (multi-tenant de base única). Diagrama de entidades principal:

```mermaid
erDiagram
    INSTITUCION ||--o{ NIVEL : tiene
    INSTITUCION ||--o{ CICLO_LECTIVO : define
    INSTITUCION ||--o{ USUARIO_ROL : autoriza
    CICLO_LECTIVO ||--o{ PERIODO_ACADEMICO : "divide en cuatrimestres"
    NIVEL ||--o{ TURNO : organiza
    TURNO ||--o{ BLOQUE_HORARIO : "grilla semanal"
    NIVEL ||--o{ CURSO : agrupa
    CURSO ||--o{ MATERIA_PLAN : "plan de estudios"

    PERSONA ||--o{ LEGAJO : "una por institucion"
    INSTITUCION ||--o{ LEGAJO : registra
    LEGAJO ||--o{ CARGO : contiene
    LEGAJO ||--o{ DOCUMENTO_LEGAJO : adjunta
    LEGAJO ||--o{ TITULO : acredita
    LEGAJO ||--o{ SERVICIO_ANTERIOR : computa
    CARGO }o--o| MATERIA_PLAN : "si es hora catedra"
    CARGO }o--o| POF_ITEM : "si es subvencionado"

    LEGAJO ||--o{ DDJJ_DISPONIBILIDAD : declara
    HORARIO_VERSION ||--o{ ASIGNACION_HORARIA : compone
    PERIODO_ACADEMICO ||--o{ HORARIO_VERSION : versiona
    ASIGNACION_HORARIA }o--|| BLOQUE_HORARIO : ocupa
    ASIGNACION_HORARIA }o--|| CURSO : para
    ASIGNACION_HORARIA }o--|| CARGO : dicta

    LEGAJO ||--o{ ASISTENCIA_REGISTRO : registra
    LEGAJO ||--o{ LICENCIA : solicita
    TIPO_LICENCIA ||--o{ LICENCIA : clasifica
    LICENCIA ||--o{ SUPLENCIA : "cubre (opcional)"
    SUPLENCIA }o--|| CARGO : "cargo cubierto"
    SUPLENCIA }o--|| LEGAJO : suplente

    CIERRE_PERIODO ||--o{ NOVEDAD : congela
    NOVEDAD }o--|| CARGO : afecta
```

**Campos clave por entidad (resumen):**

- `CARGO`: tipo (cargo_base | horas_catedra), horas_semanales, situacion_revista (titular | provisional | suplente), **fuente_pago (subvencionado | interno)**, fecha_alta, fecha_baja, resolucion.
- `TIPO_LICENCIA`: codigo, nombre, referencia_normativa, con_goce (bool), tope_dias_anual, requiere_certificado.
- `DDJJ_DISPONIBILIDAD`: legajo, periodo_academico, bloques_no_disponibles, observaciones, archivo adjunto.
- `HORARIO_VERSION`: periodo_academico, estado (borrador | vigente | historico), vigencia_desde, vigencia_hasta.
- `ASISTENCIA_REGISTRO`: legajo, cargo, fecha, estado (presente | ausente | tarde | retiro | parcial), horas_afectadas, licencia_id (nullable → injustificada si es null y ausente).
- `NOVEDAD`: periodo (mes/año), legajo, cargo, tipo, dias, horas, detalle, **destino (contralor_estatal | liquidacion_interna)** derivado de fuente_pago, estado (pendiente | informada), informada_por/fecha.
- `CIERRE_PERIODO`: mes/año, estado (abierto | cerrado | reabierto), cerrado_por, timestamp.

---

## 6. Arquitectura técnica

Elegida para un desarrollador solo, con Claude Code, y lista para crecer a SaaS.

| Capa | Elección | Motivo |
|---|---|---|
| Backend | **Python 3.12 + Django 5** | Admin gratis para soporte, ORM sólido, ecosistema maduro, ideal para CRUD pesado. |
| Base de datos | **PostgreSQL 16** | Multi-tenant confiable, integridad referencial. |
| Frontend | **Templates Django + HTMX + Alpine.js + Tailwind CSS** | Un solo deploy, sin SPA que mantener; interactividad suficiente (grillas de horarios, validación en vivo). |
| Portal docente | La misma web, **responsive + PWA** (manifest + service worker) | Instalable en el celular del docente sin app stores; geolocalización vía API del navegador para el fichaje. |
| Generador de horarios | **Google OR-Tools (CP-SAT)** | Estado del arte en timetabling; modela restricciones duras y objetivos ponderados (minimizar días de asistencia). |
| Tareas en segundo plano | **django-rq + Redis** | Generador, PDFs pesados y alertas fuera del request. Más simple que Celery. |
| PDFs | **WeasyPrint** | Certificaciones y planillas desde HTML/CSS. |
| Excel | **openpyxl** | Exports de novedades y horarios. |
| Autenticación | **django-allauth** (email + contraseña) | Roles por institución con grupos propios. |
| Multi-tenant | **Base única con `institucion_id`** en todo modelo de negocio + middleware/manager que fuerza el scoping | Simple de operar; suficiente hasta decenas de escuelas. |
| Adjuntos | Disco local (volumen) en v1; S3-compatible después | |
| Deploy | **Docker Compose** (web, worker, postgres, redis, caddy) en un VPS | Barato, reproducible, migrable a PaaS. |
| Backups | `pg_dump` diario + copia off-site | Datos laborales sensibles. |
| Tests / CI | **pytest-django** + GitHub Actions | Los cálculos de novedades y el generador exigen tests. |
| Idioma / TZ | es-AR · `America/Argentina/San_Luis` | |

**Estructura de apps Django sugerida:**

```
sge/
├── core/        # tenancy, instituciones, usuarios, roles, auditoría, configuración
├── estructura/  # niveles, ciclos, cuatrimestres, turnos, bloques, cursos, materias
├── legajos/     # personas, legajos, cargos, documentación, títulos, servicios, certificaciones
├── horarios/    # DDJJ, restricciones, versiones, generador CP-SAT, vistas/exports
├── asistencia/  # parte diario, registros, justificaciones
├── licencias/   # catálogo de tipos, solicitudes, flujo, suplencias
├── novedades/   # compilación, cierres, exports, mapeo de columnas, checklist
└── portal/      # PWA docente: horario, avisos, solicitudes, fichaje
```

**Seguridad y cumplimiento:**

- Datos personales y de salud (certificados médicos): acceso restringido por rol, cifrado en tránsito (TLS), backups protegidos. Marco: Ley 25.326 de Protección de Datos Personales.
- **Auditoría**: log inmutable de acciones sensibles (cierres de período, reaperturas, ediciones de novedades, cambios de cargos).
- Los cierres de período son inmutables salvo reapertura autorizada y auditada.

---

## 7. Roadmap por fases

Cada fase termina con algo usable en la escuela real. Sirven como unidades de trabajo para sesiones de Claude Code.

| Fase | Contenido | Resultado usable |
|---|---|---|
| **F0 · Fundaciones** | Proyecto Django, Docker, CI, auth, multi-tenant, roles, ABM de institución, niveles, ciclo lectivo, cuatrimestres, turnos, bloques, cursos y materias. | Estructura del colegio cargada. |
| **F1 · RRHH** | Personas, legajos, cargos con fuente de pago y situación de revista, documentación con vencimientos y alertas, títulos, servicios, **certificación de servicios PDF**. | Reemplaza las carpetas y planillas de legajos. |
| **F2 · Horarios** | Asignaciones docente-materia-curso, grilla manual con validación de choques, DDJJ, vistas e impresión; luego **generador CP-SAT** con objetivos ponderados, bloqueo + regeneración parcial, vigencias cuatrimestrales. | El horario 2027 se arma con el sistema. |
| **F3 · Asistencia y licencias** | Parte diario autogenerado, carga por secretaría, catálogo de licencias, flujo solicitud→aprobación, topes, **suplencias con o sin cobertura**. | Se abandona el parte en papel como registro maestro. |
| **F4 · Novedades y cierre** | Motor de compilación, separación contralor/interno, pre-cierre y cierre auditable, export Excel con mapeo al Sheet del liquidador, PDF, checklist "informada", acceso del contador. | El fin de mes baja de días a minutos. |
| **F5 · Portal docente (PWA)** | Ver horario y legajo, avisar inasistencia, solicitar licencia con adjunto; **fichaje con geolocalización** (objetivo declarado). | Docentes autogestionan; asistencia en tiempo real. |
| **F6 · Producto SaaS** | Onboarding de nuevas escuelas, configuración por jurisdicción, prefill de Google Forms / API Sheets, branding, planes y facturación, landing comercial. | Se puede vender a otra institución. |

**Orden de valor:** F0→F1→F2 primero porque el generador de horarios es la funcionalidad diferencial y valida el producto; F3→F4 completan el ciclo mensual que motiva la compra.

---

## 8. Preguntas abiertas (resolver antes o durante cada fase)

1. ~~**Planilla del liquidador**~~ → **RESUELTA**: formulario y planilla relevados, ver Anexo A. Queda pendiente para el prefill v2 obtener los **entry IDs** del Google Form (se sacan del link "Obtener enlace completado previamente" del formulario). *(F4 v2)*
2. **Régimen de licencias de San Luis:** *parcialmente resuelta* — los motivos en uso están relevados (Anexo A.3); falta confirmar por tipo: artículo/inciso, con/sin goce y topes de días. *(bloquea F3)*
3. **Formato del contralor estatal:** modelo real de la planilla/rendición que se presenta por los cargos subvencionados en San Luis. *(F4/F6)*
4. **Estructura horaria exacta:** duración de la hora cátedra, bloques por turno, recreos, turnos existentes. *(F0)*
5. **POF:** formato del documento oficial para modelar `POF_ITEM` y el control grilla vs. POF. *(F2)*
6. **Volúmenes:** *parcialmente resuelta* — el circuito actual registra ~40 novedades/mes (693 en 17 meses; 86% secundario). Falta la cantidad de docentes, cursos y divisiones para dimensionar el generador. *(F2)*
7. **Nombre comercial y dominio** del producto. *(F6)*
8. **Presupuesto de hosting** (VPS ~USD 10–20/mes al inicio). *(F0)*

---

## 9. Cómo usar este documento con Claude Code

- Trabajar **una fase por vez**; al iniciar una sesión, indicar la fase (p. ej. *"Implementá la F1 según REQUERIMIENTOS.md"*). Las fases ya están pensadas como unidades autocontenidas.
- Ante ambigüedad, este documento manda; si algo cambia, **actualizar el documento en el mismo PR** que el código.
- Las preguntas abiertas (§8) que bloquean una fase deben resolverse antes de arrancarla: conviene pegar en la sesión el material real (planillas, DDJJ, régimen de licencias) para que quede modelado con datos verdaderos.
- Pedir tests para: compilación de novedades, cómputo de antigüedad, validación de choques y restricciones del generador.

---

## Anexo A · Planilla actual del liquidador (relevada)

Relevamiento de agosto 2026 sobre la hoja de respuestas del Google Form **"Novedades Sueldos"** compartida con el liquidador. Es la referencia obligada para el export v1 (mapeo de columnas) y el prefill v2 del módulo M6.

### A.1 Volumetría

- **693 respuestas** entre marzo 2025 y agosto 2026 (~**40 novedades/mes**).
- Por nivel: Secundario ~86%, Inicial ~13%, Primario ~1%. Confirma arrancar por secundaria.
- Por tipo: **Licencia 515 · Alta 78 · Cese 39 · Renuncia 29 · Cambio 2**.
- Por planilla: **Oficial ~88% · Interna ~12%**.
- ~46 casos "SIN REEMPLAZO" (valida el flujo "sin cobertura / alumnos libres" del M5).

### A.2 Campos del formulario

El formulario repite la misma sección de campos para cada nivel (en primario "Cantidad de Horas" se llama "Cantidad de **Obligaciones**" — mantener el rótulo configurable por nivel).

| Campo del form | Valores observados / equivalencia en el sistema |
|---|---|
| Marca temporal | Automática del Form → fecha de carga de la novedad. |
| Seleccione Nivel - Área | Inicial / Primario / Secundario → nivel del cargo. |
| Seleccione la opción correspondiente | **Licencia / Alta / Cese / Renuncia / Cambio** → tipo de novedad. |
| Fecha | Inicio de la novedad o ausencia. |
| Espacio Curricular | Materia **o cargo no áulico**: Preceptor/a, Secretaria, Prosecretaría, Administrador/a, Maestra Jardinera, Jornada Extendida (Pre/Pos Hora), Tutoría, Catequesis, etc. → el sistema lo deriva del cargo. |
| Apellido y Nombre del Docente Ausente | → legajo/persona. |
| Motivo | Catálogo A.3; en las altas se repite "Alta". |
| Presenta Certificado? | Sí/No. |
| Cargar Certificado | Link a Drive → reemplazado por el adjunto de la licencia (M4). |
| Reemplazante | Nombre, **"SIN REEMPLAZO"** o vacío → suplencia (M5) o sin cobertura. |
| Jornada Completa | Sí/No (cargos de jornada vs. horas sueltas). |
| Cantidad de Horas / Obligaciones | Horas cátedra afectadas. |
| Tiempo Determinado | Sí/No → designación a término (suplencias/provisionales). |
| En caso de Licencias - Fecha de Finalización | Fin de la licencia o de la designación. |
| Planilla | **Oficial / Interna** → `destino` de la novedad (fuente de pago del cargo). |
| OBSERVACIONES | Texto libre. En las **altas** hoy se tipea ahí CUIL, obra social y antigüedad → el sistema los toma estructurados del legajo. Aparecen referencias normativas: "Art. 83" (maternidad), "ART. 100" (suplencias). |

### A.3 Motivos observados (precarga del catálogo de licencias)

Frecuencia aproximada en el período relevado; los nombres se normalizan (el form tiene typos como "Jonadas" y "Cargo Mayo"):

| Motivo (normalizado) | Frecuencia | Notas |
|---|---|---|
| Enfermedad | muy alta (~180) | Corto y largo tratamiento a distinguir. |
| Atención Familiar | alta (~95) | |
| Razones Particulares | alta (~100) | En el form: "R. Particulares" / "Particular". |
| Congresos / Cursos / Jornadas | alta (~80) | |
| Examen | media (~18) | Incluye exámenes médicos y de estudio. |
| Estudios / Investigación | media (~11) | |
| Fallecimiento Familiar | baja (~6) | |
| Maternidad | baja (~5) | Referencia "Art. 83". |
| Matrimonio | baja (~2) | 12 días según observaciones. |
| Licencia Especial sin Goce de Haberes | media (~15) | Sin goce → impacta haberes. |
| Licencia por Cargo de Mayor Jerarquía | baja (~4) | En el form: "Lic. Cargo Mayo Jerarquia". |

### A.4 Reglas derivadas del relevamiento

1. **Solo se informa lo que impacta haberes** (descuento o pago adicional): regla vigente del liquidador; el sistema registra todo pero filtra el paquete a informar.
2. Renuncia y Cese son tipos distintos de baja: mantener ambos.
3. Las altas necesitan CUIL, obra social y antigüedad: hoy van en texto libre, el sistema los saca del legajo (M1) y los incluye en el export.
4. Los certificados hoy viven en Drive del docente: pasar a adjuntos del sistema con acceso por rol.
5. El campo "Planilla" (Oficial/Interna) lo decide hoy la secretaría a mano: en el sistema se **deriva automáticamente de la fuente de pago del cargo**, eliminando errores de ruteo.
