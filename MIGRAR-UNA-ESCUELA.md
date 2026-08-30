# Cargar una escuela real en el sistema

Cómo pasar de la escuela de ejemplo a una escuela de verdad, con su gente y su
estructura. Está escrito para hacerlo en **dos conversaciones separadas**: una
que prepara los datos y otra que toca el código.

---

## 1. Antes de tocar nada: son datos de otras personas

En estos archivos hay CUIL, domicilio, teléfono y a veces datos de salud de
gente que no está en la conversación. Tres reglas:

1. **Pedile autorización a la escuela** antes de subir sus archivos a ningún
   servicio. Es la empleadora y son datos de su personal.
2. **Llevá lo mínimo.** Para ver si el sistema le sirve a la escuela alcanza
   con apellido, nombre, CUIL y los cargos. El domicilio, la obra social y los
   certificados médicos pueden esperar a que la escuela decida usarlo en serio.
3. **Empezá por diez personas, no por ciento treinta.** Si el formato está mal,
   te enterás en cinco minutos y no en dos horas.

El repositorio ya ignora `/media/`, `db.sqlite3`, `/respaldos/` y `/datos/`:
mientras los archivos reales estén en esas carpetas, no se suben a GitHub por
accidente. **Igual conviene no dejarlos en el repositorio**: una carpeta aparte
en tu computadora es mejor.

---

## 2. Quién hace qué en cada conversación

| | **Chat de datos** | **Chat de código** |
|---|---|---|
| Con qué trabaja | Las planillas reales de la escuela | El repositorio |
| Qué produce | Archivos listos para importar | Cambios en la app |
| Qué recibe | Los archivos que te dio la escuela | Pedidos de funciones y errores |
| Qué **nunca** entra | Código del sistema | Los archivos con datos reales |

La regla práctica: **el archivo con nombres y CUIL reales no se pega en el chat
de código**. Si algo del contenido hace falta acá, se resume ("hay 134 personas,
40 tienen cargos de las dos fuentes") o se manda una fila inventada de ejemplo.

---

## 3. Qué tiene que preparar el chat de datos

En el orden en que el sistema lo necesita. Los primeros cuatro se cargan a mano
en el panel (son pocos y solo se hacen una vez al año); el quinto es el que
importa por Excel.

### 3.1 La estructura del colegio

Una lista, no un archivo: es para tipear en **Administración** siguiendo el
checklist del tablero.

1. **Niveles** que tiene la escuela (inicial, primario, secundario).
2. **Ciclo lectivo** con fecha de inicio y de fin, y sus **períodos**
   (cuatrimestres o trimestres) con sus fechas.
3. **Turnos** y la **grilla horaria**: a qué hora empieza cada hora de clase,
   cuánto dura, dónde caen los recreos y si hay almuerzo. Si hay cursos con
   distinta grilla, una lista por cada esquema.
4. **Cursos y divisiones** del ciclo (1°A, 1°B, …), con su nivel y turno.
5. **Materias** y el **plan de estudios**: qué materias tiene cada curso y con
   cuántas horas semanales.

### 3.2 El personal, en Excel

Este sí se importa: **Personal → Bajar Excel** para obtener la plantilla vacía,
se completa, y **Personal → Subir planilla**. Las columnas son exactamente
estas, en este orden:

| Columna | Qué va | Obligatorio |
|---|---|---|
| CUIL | Con o sin guiones; también sirve como número | **Sí** (es la identidad) |
| Apellido | | **Sí** |
| Nombre | | **Sí** |
| DNI | | no |
| Email | Para los avisos del sistema | no |
| Teléfono | Para el WhatsApp al suplente | no |
| Fecha de ingreso | Primer día en esta escuela | **Sí para gente nueva** |
| Fecha de nacimiento | | no |
| Obra social | | no |
| Domicilio | | no |
| Localidad | | no |
| Estado | `Activo` o `De baja` | no (por omisión, activo) |
| Plantel | `Docente`, `Preceptor/a`, `Directivo`, `Administrativo` o `Maestranza` | no (por omisión, docente) |
| Materias que puede dar | Separadas por `\|` o por coma | no |

Reglas que conviene saber al armarlo:

- **El CUIL identifica.** Con el mismo CUIL se actualiza a esa persona; con uno
  nuevo se crea. Subir dos veces el mismo archivo no duplica a nadie.
- **Nadie se borra.** Una fila que falta no es una baja; las bajas se hacen
  adentro, con su motivo.
- Las **materias tienen que existir antes** en la escuela, escritas igual. Las
  que no existan se ignoran y quedan anotadas fila por fila en el informe.
- Fechas en `dd/mm/aaaa` o como fecha de Excel.

### 3.3 Los cargos

**Hoy los cargos se cargan a mano**, en el legajo de cada persona. Es a
propósito: un cargo tiene materia, curso, horas, situación de revista y fuente
de pago, y eso mal importado son errores de liquidación.

Para una escuela chica es una tarde de trabajo. Para 130 personas conviene que
el chat de datos deje la lista prolija —una fila por cargo, con **persona,
materia, curso, horas semanales, situación de revista, fuente de pago, fecha de
alta y número de resolución**— y que en el chat de código pidas el importador de
cargos.

### 3.4 Las declaraciones juradas (opcional)

Solo si querés que el sistema **genere** el horario en vez de cargarlo. Por
docente y período: en qué franjas no está disponible y por qué (otra escuela,
estudio, motivo personal).

---

## 4. El mensaje para abrir el chat de datos

Copiá esto tal cual, adjuntá `CONTEXTO-EDUCATIVO.md` y los archivos de la
escuela:

> Estoy preparando datos reales de una escuela para cargarlos en un sistema de
> gestión escolar. Necesito que me ayudes a **transformar y limpiar planillas**,
> no a programar.
>
> Te adjunto:
> - `CONTEXTO-EDUCATIVO.md`, que explica cómo funciona la escuela y el
>   vocabulario (legajo, cargo, hora cátedra, situación de revista, fuente de
>   pago).
> - Los archivos que me pasó la escuela.
>
> Lo que necesito, en este orden:
>
> 1. **Un diagnóstico** de qué hay en los archivos y qué falta para poder
>    cargarlos: cuántas personas, cuántos cargos, qué datos vienen incompletos,
>    qué inconsistencias hay (CUIL mal formados, nombres repetidos, materias
>    escritas de dos maneras).
> 2. **La estructura del colegio** en una lista ordenada para cargarla a mano:
>    niveles, ciclo y períodos con fechas, turnos y grilla horaria (hora por
>    hora, con recreos y almuerzo), cursos y divisiones, materias y plan de
>    estudios con horas semanales por curso.
> 3. **Un Excel del personal** con exactamente estas columnas, en este orden:
>    CUIL, Apellido, Nombre, DNI, Email, Teléfono, Fecha de ingreso, Fecha de
>    nacimiento, Obra social, Domicilio, Localidad, Estado, Plantel, Materias
>    que puede dar.
>    - El CUIL es la identidad (con o sin guiones).
>    - Estado: `Activo` o `De baja`. Plantel: `Docente`, `Preceptor/a`,
>      `Directivo`, `Administrativo` o `Maestranza`.
>    - Materias separadas por `|`, escritas igual que en el plan de estudios.
>    - Fechas en dd/mm/aaaa.
> 4. **Una planilla de cargos**, una fila por cargo: persona (CUIL), materia,
>    curso, horas semanales, situación de revista (titular / provisional /
>    suplente), fuente de pago (subvencionado / interno), fecha de alta y número
>    de resolución si lo hay.
>
> Importante: **preguntame cuando algo sea ambiguo** en lugar de suponer. Un
> dato inventado en una planilla de sueldos es plata de más o de menos en el
> sueldo de alguien.

---

## 5. Cómo vuelve a la aplicación

1. **Creá la escuela** en Administración → Instituciones. Ponele su nombre real,
   y **un color propio** distinto del naranja: así se distingue de un vistazo de
   la escuela de ejemplo.
2. **Cambiá a esa escuela** con el selector de la barra superior. Todo lo que
   cargues a partir de acá va a esa institución y a ninguna otra.
3. **Cargá la estructura** siguiendo el checklist del tablero, en orden.
4. **Subí la planilla del personal** (Personal → Subir planilla) y **leé el
   informe**: dice qué se creó, qué se actualizó y qué quedó observado. Corregí
   el Excel y volvé a subirlo las veces que haga falta.
5. **Cargá los cargos**.
6. **Armá el horario**: cargalo a mano, o cargá las DDJJ y generalo.
7. **Hacé un respaldo** cuando termines: `python manage.py respaldar`, y bajate
   el ZIP.

---

## 6. Cosas que conviene tener presentes

- **La escuela de ejemplo no molesta.** `cargar_piloto --reiniciar` borra solo
  la escuela llamada «Escuela Orange»: filtra por nombre y una escuela real
  nunca entra ahí. Aun así, hacé el respaldo antes de correr cualquier comando.
- **Una escuela por institución.** El sistema aísla los datos por institución:
  quien trabaja en una no ve las otras. Si probás con dos escuelas, cada una en
  la suya.
- **Los usuarios se crean aparte.** Cargar el personal no crea accesos: el
  legajo es la carpeta, el usuario es la llave. Se vinculan en el legajo, en
  «usuario del portal».
- **Antes de darle acceso a alguien de la escuela**, revisá el rol: secretaría
  ve y edita todo; dirección aprueba; el docente solo lo suyo.
- Si la escuela decide usarlo en serio, releé la sección de seguridad de
  `DESPLIEGUE.md`: contraseña por persona, bajas el mismo día, y respaldo
  semanal fuera del servidor.
