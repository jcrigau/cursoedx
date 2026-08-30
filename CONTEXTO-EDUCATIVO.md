# El contexto educativo, para quien no lo conoce

Este documento explica **cómo funciona la escuela** para la que está hecho el
sistema. No es el manual de uso (ese sale con `generar_manual`), ni la guía de
código (`CLAUDE.md`), ni el alcance del producto (`REQUERIMIENTOS.md`): es el
mundo real que esos documentos dan por sabido.

Sirve para arrancar una conversación nueva —con otra sesión de trabajo, con un
colaborador, con otra IA— sin tener que reconstruir el dominio a preguntas. Casi
todas las decisiones raras del sistema se entienden si se entiende esto.

---

## 1. La escuela, en cuatro líneas

Escuela **privada subvencionada** de la provincia de **San Luis**, Argentina.
Tiene los tres niveles (inicial, primaria, secundaria); el sistema arranca por
**secundaria**, que es la más difícil, porque ahí el personal no se designa por
"cargos" enteros sino por **horas sueltas de cada materia en cada curso**.

"Subvencionada" es la clave de todo: **una parte del personal lo paga el estado
provincial y otra parte la paga la escuela**. Conviven las dos cosas, a veces en
la misma persona.

---

## 2. Quién es quién

| Quién | Qué hace | Con el sistema |
|---|---|---|
| **Secretaría** | Es *la* usuaria. Lleva legajos, arma horarios, marca el parte diario, carga licencias, consigue suplentes y le informa las novedades al liquidador. | Todo el día, todos los días. |
| **Dirección** | Aprueba o rechaza licencias, firma certificaciones, mira cómo viene la escuela. | Entra a decidir, no a cargar. |
| **Docentes** | Dan clase. Avisan cuando faltan, piden licencias, presentan certificados. | Desde el celular (portal). |
| **Preceptores** | Acompañan a los cursos. Se designan por **horas reloj**, no cátedra. | Aparecen en el parte como todos. |
| **No docentes** | Administrativos, maestranza, ordenanzas. Tienen legajo, licencias y antigüedad igual que el resto. | Están en el sistema, pero nunca cubren un curso. |
| **Liquidador** | Contador **externo** a la escuela. Recibe las novedades del mes y arma los sueldos. | Solo descarga lo ya cerrado. |
| **El organismo provincial** | Financia los cargos subvencionados y controla que se usen como se aprobó. | No entra al sistema; se le rinde en papel. |

---

## 3. El vocabulario mínimo

| Palabra | Qué significa acá |
|---|---|
| **Legajo** | La carpeta de una persona: datos, cargos, títulos, documentación, historial. Una persona, un legajo. |
| **Cargo** | Una designación concreta. Puede ser un cargo entero (preceptor, secretaria, maestra de grado) o **un paquete de horas** de una materia en un curso. **Una persona tiene varios cargos a la vez.** |
| **Hora cátedra** | La unidad de secundaria: 40 minutos. "Tiene 5 horas de Matemática en 3°B" es un cargo. Los preceptores se miden en **horas reloj** de 60. |
| **Situación de revista** | Cómo está designada esa persona en ese cargo: **titular** (el puesto es suyo), **provisional/interino** (lo ocupa hasta que se titularice) o **suplente** (reemplaza a alguien). |
| **Fuente de pago** | Quién paga **ese cargo**: **subvencionado** (el estado) o **interno** (la escuela). |
| **POF / resolución** | La planta aprobada por el estado. Acá no hay un documento único: cada cargo subvencionado tiene **su resolución individual**, que es el respaldo de que ese sueldo se puede cobrar. |
| **DDJJ de horarios** | Declaración jurada del docente: en qué otras escuelas trabaja y cuándo. Es el insumo para armar el horario sin superponerle nada. |
| **Novedad** | Cualquier hecho del mes que **mueve plata**: un alta, una baja, una licencia sin goce, una inasistencia, una llegada tarde, una suplencia. |
| **Parte diario** | Quién vino y quién no, hoy. |
| **Alumnos libres** | Una hora que quedó sin docente y sin suplente: el curso se queda sin clase. Es una decisión válida, y hay que dejarla registrada. |
| **Contralor** | La rendición periódica al organismo que financia los cargos subvencionados. |

---

## 4. La plata: lo más contraintuitivo del dominio

Si hay que retener una sola cosa de este documento, es esta.

> **La fuente de pago es del cargo, nunca de la persona.**

No existe "un docente subvencionado". Existe una persona que tiene *estas* horas
pagadas por el estado y *aquellas otras* pagadas por la escuela. Es el caso
**mixto**, y es común.

De ahí sale todo lo demás:

- Hay **dos planillas** de sueldos: la **Oficial** (lo que paga el estado) y la
  **Interna** (lo que paga la escuela).
- Cada novedad va a la planilla **del cargo que la originó**. Una licencia de
  una persona con cargos de las dos fuentes genera **dos líneas**, una en cada
  planilla. Eso no es un error: es exactamente lo que hay que informar.
- Pero **varios cargos de la misma fuente son una sola línea**. Si alguien tiene
  tres cargos de Matemática pagados por el estado y falta un día, es **un** día
  de descuento, no tres. Informarlo tres veces es triplicarle el descuento a una
  persona real.

Dos precisiones que evitan malentendidos:

1. **El sistema no liquida sueldos.** Compila novedades. Los sueldos los hacen
   el estado y el liquidador externo.
2. **Solo se informa lo que genera descuento o pago adicional.** El sistema
   registra todo, pero al liquidador se le manda únicamente lo que mueve dinero.
   (Antes se le mandaba de más y pidió que se dejara de hacer.)

---

## 5. Los ritmos

La escuela vive en tres ciclos, y el sistema está organizado igual.

**El día.** A las 7:45 empieza el turno mañana. Antes de esa hora la secretaría
necesita saber quién falta, qué cursos quedan sin clase y a quién llamar. Los
avisos de los docentes suelen llegar entre las 6 y las 7:30, por WhatsApp.
Después de las 7:45, cualquier cosa que no esté resuelta es un curso con 25
chicos sin profesor.

**El mes.** Se compilan las novedades, se revisan, se le informan al liquidador
y se cierra el mes. Un mes cerrado ya no se toca: si aparece algo, se reabre
dejando constancia. Son unas 40 novedades mensuales en la escuela piloto.

**El año.** El **ciclo lectivo** va de marzo a diciembre y se divide en
**cuatrimestres** (algunas materias cambian de un cuatrimestre al otro, y por
eso el horario se arma **por período**, no por año). En febrero se rearma casi
todo: mismos cursos, mismas materias, algunas designaciones nuevas.

---

## 6. Licencias: el régimen de San Luis

Las licencias no son "días libres": cada una es **un artículo del estatuto
docente provincial**, con sus propias reglas. Estas son las que usa la escuela:

| Artículo | Para qué | Topes |
|---|---|---|
| **Art. 76** | Enfermedad / estudio médico | 60 días al año; se puede extender con junta médica |
| **Art. 83** | Maternidad | 180 días por caso |
| **Art. 91** | Atención de familiar enfermo | 30 días al año |
| **Art. 93.1** | Matrimonio | 12 días por caso |
| **Art. 93.2** | Fallecimiento de familiar | según el vínculo |
| **Art. 93.3** | Nacimiento de hijo (padre) | — |
| **Art. 93.4** | Razones particulares | 5 días al año |
| **Art. 94.1** | Exámenes | 20 días al año, máximo 5 seguidos |
| **Art. 97** | Congresos, cursos y jornadas | — |
| **Art. 98** | Deportiva | — |
| **Art. 100** | Cargo de mayor jerarquía | — |
| **Art. 107** | Binomio madre-hijo | — |

Lo que hay que saber de cada licencia:

- **Con goce o sin goce.** Si es sin goce, hay descuento y por lo tanto hay
  novedad. Si es con goce, la persona cobra igual y no se informa nada.
- **Requiere certificado** o no. El certificado llega después del aviso, y a
  veces no llega nunca: ese es el agujero por donde una ausencia se convierte en
  injustificada sin que nadie se dé cuenta.
- **Topes**: por año, por caso y de días consecutivos. Pasarse tiene
  consecuencias para la persona, así que el sistema avisa al cargar.
- Una licencia puede afectar **todos los cargos** de la persona o solo algunos
  (por ejemplo, si da clases en dos niveles y solo se ausenta de uno).

---

## 7. Suplencias: cómo se cubre una ausencia

1. Alguien falta y hay una **licencia** que lo respalda.
2. La escuela decide, cargo por cargo: **designar un suplente** o **dejar el
   curso sin clase** (alumnos libres). Las dos son decisiones válidas; lo que no
   se puede es no decidir.
3. Si se designa suplente, esa persona **recibe su propio cargo** por el tiempo
   de la suplencia. Eso es un **alta** para la liquidación, y cuando termina es
   una **baja**.

Tres reglas que no son obvias:

- **Una suplencia se apoya siempre en una licencia.** Sin licencia cargada no
  hay nada que justifique la designación ni el pago.
- **Al suplente hay que avisarle.** Designar no es avisar: hasta que alguien lo
  llama, no sabe que mañana tiene que estar. En la escuela real esto se hace por
  WhatsApp.
- **Hay que revisar que no se le pisen las horas** con lo que ya da o con otra
  suplencia que ya tomó. Si no, dos cursos esperan a la misma persona a la misma
  hora.

---

## 8. Horarios: por qué son difíciles

- La grilla **no es uniforme**. Las horas van de a pares con recreos de duración
  variable, y **algunos cursos cortan para almorzar y otros no**. Dos cursos
  pueden tener "la tercera hora" en momentos distintos del reloj.
- Por eso los choques **se comparan por hora del reloj**, nunca por "número de
  bloque".
- Los docentes suelen trabajar en **varias escuelas**, y su DDJJ dice cuándo no
  están disponibles. Armar el horario es hacer entrar todo eso junto.
- Un horario armado a mano lleva semanas. El sistema lo genera y, además,
  intenta que cada docente venga la menor cantidad de días posible: para alguien
  que reparte horas entre tres escuelas, eso es su vida cotidiana.

---

## 9. Qué sale caro si se hace mal

Ordenado por gravedad. Es la lista que explica por qué el sistema es
desconfiado en ciertos lugares:

1. **Una línea de más o de menos en la planilla** es plata de más o de menos en
   el sueldo de alguien. De acá sale la obsesión con no duplicar novedades.
2. **Un dato laboral de una escuela visto desde otra.** El sistema es
   multi-escuela: una consulta mal filtrada expone sueldos y licencias ajenas.
3. **Un certificado médico abierto por quien no corresponde.** En los legajos
   hay datos de salud. Los docentes tienen usuario del sistema, así que "estar
   conectado" nunca puede alcanzar para abrir el archivo de otro.
4. **Un curso sin profesor y sin que nadie se entere.** Son 25 chicos sueltos en
   el pasillo.
5. **Un cargo subvencionado sin su resolución.** Se está cobrando algo cuyo
   respaldo no está: eso vuelve rechazado del contralor.
6. **Perder la base sin respaldo.** Son los legajos completos de la escuela.

---

## 10. Cómo habla la escuela

Importa para escribir cualquier texto que se le muestre a alguien:

- **Español rioplatense, de vos.** "Tildá", "cargala", "fijate". Nada de "usted"
  ni de neutro latinoamericano.
- **Las palabras de la escuela, no las del software.** Se dice *legajo*, *cargo*,
  *parte*, *planilla*, *novedad*, *suplente*. No se dice *usuario*, *entidad*,
  *registro* ni *ítem*.
- **Los mensajes explican qué hacer**, no qué falló. "Tildá al menos un cargo
  para cubrir" en lugar de "selección inválida".
- Toda la interfaz, los nombres de los campos y los mensajes de error están en
  español. Quien lee la pantalla es una secretaria con mucho trabajo, no un
  informático.

---

## 11. Lo que el sistema deliberadamente no hace

- **No liquida sueldos** (ver punto 4).
- **No gestiona alumnos**: ni notas, ni boletines, ni asistencia de alumnos, ni
  comunicación con familias, ni cuotas. Los cursos existen solo como estructura
  para los horarios.
- No maneja inventario, ni biblioteca, ni comedor.

---

## 12. Si esto se lleva a otra escuela

El sistema apunta a servir a varias instituciones, así que conviene saber qué
cambia de una escuela a otra. **Nada de esto se puede dar por fijo:**

- El **régimen de licencias** (los artículos y los topes son provinciales).
- El **formato de la planilla** que espera cada liquidador.
- La **grilla horaria**: duración de la hora, recreos, almuerzo, turnos.
- Si la escuela **rinde directo al estado** o le informa a un liquidador
  externo, como el piloto.
- Qué mezcla de personal subvencionado e interno tiene (una escuela puede ser
  toda privada, sin aporte estatal).

Lo que sí es común a cualquier escuela argentina de gestión privada: legajos,
cargos con situación de revista, licencias por artículo, suplencias, parte
diario y novedades mensuales.

---

## 13. Para arrancar una conversación con esto

Si estás leyendo este documento para ayudar en el proyecto, el resumen es:

> Es un sistema para la **secretaría** de una escuela privada subvencionada
> argentina. Su trabajo es que a fin de mes la escuela le informe al liquidador
> **exactamente** las novedades que corresponden —ni una de más— y que a la
> mañana ningún curso se quede sin profesor sin que alguien lo sepa. Todo lo
> demás es consecuencia de esas dos cosas.

Los otros documentos del repositorio:

- `REQUERIMIENTOS.md` — alcance, módulos y roadmap por fases. Fuente de verdad.
- `CLAUDE.md` — cómo está construido y las reglas de arquitectura.
- `DESPLIEGUE.md` — cómo se pone en marcha y cómo se cuida.
- `CHANGELOG.md` — qué cambió en cada versión.
- El **manual de la secretaría** en PDF: `python manage.py generar_manual`.
