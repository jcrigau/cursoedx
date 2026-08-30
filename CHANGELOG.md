# Historial de versiones

Qué cambió en cada versión del SGE, en orden inverso. La versión que está
corriendo se ve al pie de cualquier pantalla, y con más detalle en
**Estado del sistema** (o con `python manage.py mostrar_version`).

La numeración acompaña las fases del plan (`REQUERIMIENTOS.md` §7): la minor
sube al terminar cada fase. El **1.0 queda reservado** para cuando el sistema
esté en uso diario en una escuela, con un ciclo lectivo completo encima.

---

## Sin publicar

### Agregado

- **Planilla única para cargar una escuela nueva**
  (`python manage.py plantilla_carga`): un Excel con una hoja por cosa
  —escuela, niveles, ciclo y períodos, turnos, grilla horaria, cursos,
  materias, plan de estudios, personal, cargos, y las opcionales licencias,
  documentación y disponibilidad—, con las columnas que el sistema espera,
  desplegables con los valores válidos y **filas de ejemplo ya completadas**
  en cada hoja. Es lo que se le manda a una escuela que quiere probar el
  sistema con sus datos.
- Las filas de ejemplo van marcadas (empiezan con `EJEMPLO`) y **los
  importadores las saltean solas**: una muestra que vuelve sin borrar no crea
  a una persona inventada. La planilla del personal, cuando todavía no hay
  nadie cargado, también sale con su ejemplo.

### Corregido

- **Una falta se informaba una vez por cargo, no por planilla.** Alguien con
  tres cargos de Matemática generaba tres líneas de «2 hs» por una ausencia
  parcial de dos horas: seis horas informadas al liquidador. Ahora es una
  línea por planilla —el mismo criterio que ya usaban las tardanzas—, y la
  fuente de pago sigue separando cuando corresponde.
- **Una falta de día entero se exportaba con las horas semanales del cargo.**
  El export toma las horas si están, así que «faltó un día» salía como «10».
  Un día entero se informa en días y una ausencia parcial en las horas que
  realmente no dio; nunca las dos cosas.
- **Al recompilar se quitan las novedades automáticas que ya no corresponden**
  (una licencia anulada, una falta corregida, líneas repetidas de una versión
  anterior). No se toca lo cargado a mano ni lo congelado por un cierre.

### Seguridad

- **Cada archivo se autoriza contra su dueño, no contra el login.** Los
  docentes tienen usuario del portal: hasta ahora, con estar conectado y
  adivinar una dirección se podía abrir el certificado médico de otro. Ahora
  se comprueba de qué registro cuelga cada archivo y quién lo pide; lo propio
  siempre se puede ver, y lo que no cuelga de nada no se entrega.
- **Los nombres no se pueden adivinar**: cada adjunto se guarda en una carpeta
  con identificador al azar.
- **Solo se suben papeles y fotos**: lista blanca de extensiones y tope de
  10 MB. Quedan afuera `.html` y `.svg`, que el navegador ejecuta y servirían
  para robarle la sesión a un compañero. Lo que no se puede mostrar sin riesgo
  se entrega como descarga, y siempre con `nosniff`.
- **El ingreso se registra y se frena**: cada intento queda anotado y, tras
  cinco fallos seguidos, esa dirección desde esa computadora espera quince
  minutos (con un tope más alto por IP para cortar un barrido). Entrar bien
  limpia la cuenta. El bloqueo queda en la bitácora.
- **Los borrados del panel quedan registrados**: quién borró qué y cuándo. El
  respaldo permite recuperarlo; esto permite darse cuenta.
- **Sesión de ocho horas** que se renueva mientras se trabaja, en lugar de dos
  semanas: la computadora de secretaría la usan varias personas.
- **Contraseñas de diez caracteres** como mínimo.
- **El navegador solo acepta contenido propio** (política de seguridad de
  contenido): nada de recursos externos, ni el sistema dentro de un iframe
  ajeno, ni formularios apuntando a otro servidor.
- La **dirección del panel** se puede cambiar en el `.env` (`SGE_URL_PANEL`).

### Lo demás

- **Cubrir toda una licencia de una vez**: la pantalla lista los cargos que
  deja libres, se tildan los que van a la misma persona y se designan juntos.
  Antes era un formulario por cargo. Antes de guardar, el sistema cruza esas
  horas con lo que el suplente ya da —y con las suplencias que ya tomó—
  comparando horarios reales: si algo se pisa, **no guarda nada** y dice qué
  hora es. También sirve para dejar varios cargos sin cobertura de una vez.
  La lista de suplentes viene **ya evaluada**: adelante los que tienen esas
  horas libres (con la marca de quién da la materia) y plegados los que no,
  cada uno con la hora que se le pisa. Al terminar ofrece avisarle, y el
  mensaje nombra todos los cargos asignados, no uno solo.
- **Respaldo en un comando** (`respaldar`): un ZIP con la base de datos y todos
  los archivos subidos, con rotación de los últimos ocho. Se programa semanal
  y se baja del servidor. Una copia de la base sin los certificados deja
  legajos incompletos, por eso van juntos.
- **`probar_correo`**: manda un mensaje de prueba, muestra la configuración
  —nunca la contraseña— y traduce los errores típicos («con Gmail va una
  contraseña de aplicación», «el hospedaje bloquea el correo saliente»).
- **La documentación se reclama sola** (`reclamar_documentacion`): al docente
  que se le vence el apto o los antecedentes le llega el aviso por correo, con
  copia a secretaría, y no se le insiste antes de dos semanas.
- **El legajo completo en PDF**: datos, cargos, títulos, servicios anteriores y
  documentación en un documento, para la junta o una inspección. Queda
  registrado en la auditoría porque sale de la escuela con datos personales.
- **Calendario mensual de licencias**: el mes entero, con quién falta cada día
  y las licencias sin aprobar punteadas. Es lo que hay que mirar antes de
  autorizar una más.
- **Control de la planta**: cruza las horas designadas en los cargos con las
  que realmente se dan en el horario, y marca los cargos subvencionados sin
  número de resolución —donde se cobra algo cuyo respaldo no está cargado—.
- **Ausentismo**: los últimos doce meses en un gráfico, separando días de
  licencia de inasistencias sin licencia, con el detalle por motivo y la tabla
  de números al lado. El gráfico es SVG propio, sin librerías.
- **Personal no docente**: cada legajo dice su **plantel** —docente,
  preceptor/a, directivo, administrativo o maestranza/ordenanza—. Personal se
  filtra por plantel, a quien no da clases no se le piden materias, y
  administrativos y maestranza no aparecen al buscar reemplazos para un curso.
  La planilla Excel lleva y trae la columna «Plantel» escrita como sea
  («Ordenanza» también vale).
- **Los adjuntos ahora se ven en el servidor, y solo con sesión iniciada**:
  Django no sirve los archivos subidos cuando no está en modo desarrollo, así
  que en producción las fotos y los certificados quedaban guardados pero daban
  404. Los sirve la aplicación, detrás de login: en esa carpeta hay aptos
  psicofísicos y certificados de antecedentes, que no pueden quedar públicos.
  En el hosting **no** hay que mapear `/media/`.
- **Los archivos del legajo se abren desde la ficha**: lo que se subió en
  Documentación y en Títulos (certificados, aptos, títulos escaneados) tiene su
  «Ver archivo», sin pasar por el panel.
- **Foto tipo carnet en el legajo**: se sube desde el panel (JPG o PNG,
  cuadrada tipo 4x4; si no lo es, se recorta al mostrarla) y aparece en la
  ficha, en el listado de Personal, en la búsqueda de personas y en la
  pantalla de materias. Quien no tiene foto se muestra con una silueta
  estándar. La escuela de ejemplo trae ocho caras cargadas por
  `cargar_piloto` (no pisa una foto puesta a mano).
- **El aviso del docente llega con ruido**: al enviarlo desde el portal sale
  un **correo a secretaría y dirección** en el momento, y queda al frente del
  tablero como **«Comunicaciones sin responder»** (tarjeta y pendiente urgente
  para los dos puestos). La pantalla nueva **Avisos** lo responde con un
  toque: **Visto ✓** (el docente lo ve como «visto por secretaría» en su
  portal), **WhatsApp** o **correo** con el mensaje ya escrito —incluido el
  recordatorio del certificado cuando es enfermedad— y «Cargar la licencia»
  con la persona y la fecha puestas. El directivo también puede responder.
- **Los cursos hoy**: el día visto por curso, hora por hora, con la materia y
  el docente que la da. Las horas que quedan sin clase salen marcadas en rojo,
  las cubiertas por un suplente en el color de la escuela. Sale del mismo cruce
  que el parte diario, así que las dos pantallas no pueden contradecirse.
- **Identidad visual por escuela**: color y emblema propios, que pintan el
  encabezado de todas las pantallas mientras se trabaja en esa institución. La
  escuela de ejemplo pasó a llamarse **Orange**, en naranja y con una naranja
  por emblema, para que nunca se confunda con la real. Sin escuela activa no se
  aplica ningún color.
- **Portada del admin** con el mismo menú lateral que el resto del panel —
  Django lo escondía solo ahí— y accesos directos al trabajo del día.
- **Manual de la secretaría** en PDF, generado desde el propio sistema
  (`generar_manual`), y **control de versiones** visible al pie de cada
  pantalla y en `/sistema/`.
- **La semana que viene**, **la ficha de la persona**, y el **resumen del mes
  abrible** día por día.
- **El personal por planilla**: se baja el Excel, se corrige o se agregan
  filas, y se vuelve a subir. El CUIL identifica; nada se borra por faltar.
- **El resumen del día por correo** (`enviar_resumen_diario`, para programar
  a las 7:00) y **el año nuevo copiado del anterior** (`abrir_ciclo`).
- **Cabos sueltos**: los avisos viejos sin licencia cargada aparecen en el
  tablero. **Lo último que pasó**: la bitácora, legible, en el inicio.
- **«Cubrir ahora»**: desde cada hora en rojo, la lista de posibles reemplazos
  con filtros —está en la escuela, da la materia, disponible—, designación en
  un clic, y el aviso al suplente por email o WhatsApp.
- **Personal**: la planta completa en una pantalla, con las **materias que cada
  uno puede dar** para tildar. Es lo que alimenta la búsqueda de reemplazos.
- **La búsqueda ignora tildes**: «benitez» encuentra a Benítez.
- **Las tarjetas del tablero llevan al dato**.
- **Las decisiones se toman donde aparece el problema**: designar suplente o
  dejar sin cubrir desde el propio parte, cargar la licencia desde el aviso del
  docente, y extender o cesar suplencias desde el tablero.
- **Buscar una persona** por apellido, nombre o CUIL desde la barra.
- **Cada novedad dice de dónde salió**, con link al hecho que la generó.
- **Cómo funciona el sistema** (`/circuito/`): el camino completo dibujado, de
  el aviso del docente hasta la descarga del liquidador, con link a cada paso.
- **Ayuda plegable** en el parte, los cursos y el mes, y una **bienvenida por
  puesto** la primera vez que alguien entra.
- **El checklist de puesta en marcha** lleva a cada formulario de alta.
- **El tablero cambia según el puesto**: cada uno entra y ve lo que tiene
  para resolver, con el link al lugar exacto donde se resuelve. El directivo
  sus licencias a aprobar, la secretaría el parte y el cierre del mes, el
  liquidador lo que ya está cerrado. El docente va derecho al portal.
- **`--reiniciar`**: vacía la escuela de ejemplo y la rearma de cero, sin
  tocar ninguna otra institución. Para bases que quedaron con datos de
  versiones anteriores.
- **cargar_escenario**: un día de trabajo por resolver, con un usuario por
  puesto y el recorrido impreso al terminar.
- El **menú lateral del admin** queda fijo mientras se recorre un listado
  largo, en vez de perderse arriba.
- **cargar_demo**: deja la escuela de ejemplo en marcha, con horario publicado,
  parte del día y mes de novedades compilado.

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
