# Poner el SGE en internet

Dos caminos, según para qué sea.

| | **PythonAnywhere** | **Docker en un VPS** |
|---|---|---|
| Para qué sirve | Mostrar el sistema, probarlo con datos reales, que lo vea la escuela | Uso diario de verdad, varias escuelas |
| Costo | Gratis (con límites) o USD 5/mes | Desde USD 0 (free tier de Oracle Cloud) o USD 5-10/mes |
| Dificultad | Todo por el navegador, sin terminal propia | Requiere manejar un servidor |
| Base de datos | SQLite o MySQL | PostgreSQL |

Para la **versión de prueba**, PythonAnywhere es la opción correcta: se sube por
la web, no hay que administrar nada y queda con una dirección pública del tipo
`usuario.pythonanywhere.com`.

---

## A · PythonAnywhere paso a paso

### 0. Antes de empezar: ¿cuenta nueva o la que ya tenés?

**Cuenta gratuita:** permite **una sola aplicación web**. Si ya tenés otro
proyecto publicado ahí, el SGE no entra como segunda app.

**Cuenta paga:** suele permitir más de una. La forma de saberlo sin adivinar es
entrar a la pestaña **Web**: si aparece *Add a new web app*, hay lugar. Dos
detalles a tener en cuenta antes de decidir:

- El subdominio `usuario.pythonanywhere.com` es **uno por cuenta**; las apps
  adicionales normalmente necesitan un dominio propio. Verificalo al agregarla.
- Las dos apps **comparten disco, CPU y base de datos** de la misma cuenta. El
  generador de horarios consume CPU del mismo pozo que el otro proyecto, y un
  descuido de espacio afecta a los dos.

**Para un sitio de prueba temporal** —que es de lo que se trata hasta que el
sistema entre en funcionamiento— lo más conveniente es una **cuenta gratuita
nueva, dedicada al SGE**: no cuesta nada, no toca los recursos de otro
proyecto, y el día que se descarta no queda nada colgando. Después, para el uso
real de una escuela, se pasa a un plan pago o a un servidor propio (opción B).

### 1. Crear la cuenta

En https://www.pythonanywhere.com → **Pricing & signup** → *Create a Beginner
account* (gratis). El nombre de usuario que elijas va a ser parte de la
dirección web, así que conviene algo presentable.

### 2. Traer el proyecto

Pestaña **Consoles** → *Bash*. En la consola:

```bash
git clone https://github.com/jcrigau/cursoedx.git
cd cursoedx
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Si se queda sin espacio** (la cuenta gratuita tiene 512 MB): el paquete
> pesado es OR-Tools, el que genera los horarios. Se puede sacar con
> `pip uninstall ortools` y el resto del sistema funciona igual —los horarios
> se cargan a mano y las demás pantallas no se enteran—. Para tener el
> generador andando conviene el plan Hacker (USD 5/mes), que da 3 GB.

### 3. Configurar las variables

Todavía en la consola, dentro de `~/cursoedx`:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Editá el `.env` (pestaña **Files**, o `nano .env`) y dejalo así, con **tu**
usuario y **tu** clave generada:

```
SGE_SECRET_KEY=la-clave-larga-que-generaste
SGE_DEBUG=0
SGE_ALLOWED_HOSTS=USUARIO.pythonanywhere.com
SGE_CSRF_TRUSTED_ORIGINS=https://USUARIO.pythonanywhere.com
SGE_DATABASE_URL=
SGE_TIME_ZONE=America/Argentina/San_Luis
```

`SGE_DATABASE_URL` vacío usa SQLite, que para una prueba alcanza y sobra —y es
lo que corresponde en la cuenta gratuita, porque desde 2026 MySQL quedó
reservado a los planes pagos para las cuentas nuevas. Si tenés MySQL
disponible (pestaña **Databases**), poné:
`SGE_DATABASE_URL=mysql://USUARIO:CLAVE@USUARIO.mysql.pythonanywhere-services.com/USUARIO$sge`
e instalá el conector con `pip install mysqlclient`.

### 4. Preparar la base y los archivos estáticos

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py cargar_piloto --email vos@tuescuela.edu.ar --password una-clave-larga
```

El último comando carga la escuela de ejemplo con datos de muestra. Para
arrancar con la escuela real, salteálo y creá tu usuario con
`python manage.py createsuperuser`.

### 5. Crear la aplicación web

Pestaña **Web** → *Add a new web app* → **Manual configuration** (no "Django")
→ **Python 3.11**.

Después, en esa misma pestaña:

1. **Virtualenv**: escribí `/home/USUARIO/cursoedx/.venv`
2. **Code** → *WSGI configuration file*: abrilo, borrá todo y pegá el contenido
   de `despliegue/pythonanywhere_wsgi.py` de este repositorio, cambiando
   `USUARIO` por tu usuario.
3. **Static files**: agregá una entrada
   - URL: `/static/`
   - Directory: `/home/USUARIO/cursoedx/staticfiles`
4. **Security**: activá *Force HTTPS*.
5. Botón verde **Reload**.

Listo: `https://USUARIO.pythonanywhere.com`.

### 6. Generar el horario en la cuenta gratuita

La cuenta gratuita da 100 segundos de CPU por día, y el generador usa varios
segundos por corrida. Conviene generarlo desde la consola y con un límite
corto, en vez de hacerlo desde el navegador:

```bash
cd ~/cursoedx && source .venv/bin/activate
python manage.py generar_horario 1 --segundos 20
```

Con el plan Hacker (2000 segundos de CPU) se puede generar cómodamente desde el
panel de administración.

### 7. Actualizar cuando haya cambios

```bash
cd ~/cursoedx && source .venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py sincronizar_permisos
```

Y **Reload** en la pestaña Web.

### Qué esperar de la cuenta gratuita

- La app se "duerme" si no se usa y tarda unos segundos en despertar.
- Una app sin uso **se desactiva al mes** (antes eran tres): hay que entrar y
  apretar el botón que la reactiva. PythonAnywhere avisa por mail.
- Solo una aplicación web por cuenta (ver el punto 0).
- Los PDF pueden salir como página web si faltan librerías del sistema: se
  imprimen desde el navegador con **Ctrl+P → Guardar como PDF**, y el documento
  es el mismo.

---

## Usar un dominio propio

Registrar el dominio es **solo el nombre**. Para que alguien escriba
`sge.miescuela.com.ar` y le abra el sistema hacen falta tres cosas más:

1. **Hosting** donde corra la aplicación.
2. **DNS** que apunte el nombre a ese hosting.
3. **Certificado HTTPS**, o el navegador va a mostrar "sitio no seguro".

### Lo primero a saber

**La cuenta gratuita de PythonAnywhere no admite dominio propio**: solo
funciona `usuario.pythonanywhere.com`. El dominio requiere un plan pago. Así
que la decisión del dominio y la del plan van juntas.

Para un sitio de prueba, el subdominio gratuito alcanza y sobra. El dominio
propio recién vale la pena cuando el sistema se muestra a otras escuelas.

### El trámite en NIC.ar

Registrar un `.com.ar` se hace en https://nic.ar y requiere **Clave Fiscal de
ARCA (ex AFIP)**: la cuenta de NIC se valida con ella, así que hay que tenerla
a nombre de quien va a figurar como titular. El registro es anual y se renueva.

Conviene registrarlo a nombre de quien va a ser dueño del producto, no de la
escuela: si mañana se vende a varias instituciones, el dominio es tuyo.

### Cómo se conecta

El camino más simple y sin costo extra:

1. Registrar el dominio en NIC.ar.
2. Crear una cuenta gratuita en **Cloudflare** y agregar el dominio. Cloudflare
   da dos servidores de nombres.
3. En NIC.ar, en *Delegaciones*, cargar esos dos servidores de Cloudflare.
4. En Cloudflare, crear el registro que apunta al hosting:
   - **PythonAnywhere (plan pago):** un `CNAME` de `www` hacia la dirección que
     te da la pestaña Web, y activar el certificado desde ahí.
   - **VPS propio:** un registro `A` con la IP del servidor. El certificado lo
     emite Caddy solo, gratis.

La propagación tarda entre minutos y algunas horas.

### Lo que hay que cambiar en el sistema

Solo dos variables del `.env`, y **Reload** (o `docker compose up -d`):

```
SGE_ALLOWED_HOSTS=sge.miescuela.com.ar
SGE_CSRF_TRUSTED_ORIGINS=https://sge.miescuela.com.ar
```

Sin la segunda, los formularios empiezan a fallar con un error de CSRF: es el
olvido más habitual al mudar un sistema a su dominio.

---

## B · Docker en un servidor propio

Cuando el sistema pase de la prueba al uso diario:

```bash
git clone https://github.com/jcrigau/cursoedx.git && cd cursoedx
cp .env.example .env          # completar SGE_SECRET_KEY y SGE_ALLOWED_HOSTS
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

Levanta PostgreSQL, la aplicación y las tareas de arranque. Incluye las
librerías para los PDF, así que ahí sí salen siempre en PDF.

Para exponerlo a internet sin servidor propio ni IP fija, sirve **Cloudflare
Tunnel** desde una PC de la escuela.

### Copias de seguridad (importante)

Son datos laborales: hacé una copia diaria y guardala fuera del servidor.

```bash
docker compose exec db pg_dump -U sge sge > respaldo-$(date +%F).sql
```

En PythonAnywhere, con SQLite, alcanza con descargar `db.sqlite3` desde la
pestaña **Files** y guardar también la carpeta `media/` (los adjuntos de los
legajos).
