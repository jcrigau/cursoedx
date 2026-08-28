"""Archivo WSGI para PythonAnywhere.

Copiar el contenido en el archivo WSGI que PythonAnywhere crea para la app
(pestaña **Web** → *WSGI configuration file*), reemplazando **todo** lo que
traiga por defecto, y cambiando USUARIO por el nombre de tu cuenta.
"""

import os
import sys

# 1. Que Python encuentre el proyecto.
RUTA_PROYECTO = "/home/USUARIO/cursoedx"
if RUTA_PROYECTO not in sys.path:
    sys.path.insert(0, RUTA_PROYECTO)

# 2. Configuración. La clave secreta y el resto de las variables se cargan del
#    archivo .env del proyecto (ver DESPLIEGUE.md).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 3. La aplicación.
from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
