# SGE — Sistema de Gestión para Secretaría Escolar

Producto SaaS para secretarías de escuelas de gestión privada (primer caso: escuela privada subvencionada de San Luis, Argentina). Resuelve la operación del personal docente:

- **RRHH / Legajos** — cargos con fuente de pago (subvencionado/interno), documentación con vencimientos, certificación de servicios.
- **Horarios** — generador automático a partir de DDJJ y restricciones (minimiza los días de asistencia de cada docente), vigencias cuatrimestrales.
- **Asistencia** — parte diario autogenerado, justificaciones.
- **Licencias y suplencias** — catálogo configurable, cobertura opcional ("sin reemplazo" → alumnos libres).
- **Novedades para liquidación** — compilación mensual separada en Planilla Oficial (contralor estatal) y Planilla Interna (liquidación de la escuela), con cierre auditable.

**Estado:** definición de requerimientos.

📄 Documento principal: **[REQUERIMIENTOS.md](REQUERIMIENTOS.md)** — visión, módulos, modelo de datos, arquitectura (Django + PostgreSQL + OR-Tools) y roadmap por fases.
