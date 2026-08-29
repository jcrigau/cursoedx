"""Los archivos que sube la escuela: fotos, certificados, títulos.

En desarrollo Django los sirve solo; en producción, no. La guía de despliegue
mandaba mapear `/static/` en el hosting, pero nunca `/media/`: por eso una
foto o un certificado subido quedaba guardado y aun así el navegador recibía
un 404.

Se sirven desde acá, y **solo a quien esté conectado**: en esta carpeta hay
aptos psicofísicos y certificados de antecedentes, o sea datos de salud y
personales. Servirlos con un mapeo del hosting los dejaría públicos para
cualquiera que adivine la dirección.

Para una escuela —unos cientos de archivos chicos— el costo de que los sirva
Django es irrelevante. Si algún día el volumen lo justifica, se pasa a un
servidor de archivos con URLs firmadas.
"""

from django.contrib.auth.decorators import login_required
from django.views.static import serve as servir_archivo


@login_required
def servir_media(request, path):
    """Entrega un archivo de MEDIA_ROOT a un usuario conectado."""
    from django.conf import settings

    # django.views.static.serve resuelve la ruta contra document_root y
    # rechaza los intentos de salirse de la carpeta.
    return servir_archivo(request, path, document_root=settings.MEDIA_ROOT)
