"""La geometría de los gráficos, calculada acá y dibujada en SVG a mano.

El sistema no carga librerías de gráficos: tiene que andar con internet
intermitente y sin build. Un SVG hecho a medida pesa nada, se imprime bien y
no depende de nadie. Lo único que necesita es que las cuentas —escalas,
posiciones, altos— se hagan en Python, porque las plantillas de Django no
hacen aritmética.
"""

from dataclasses import dataclass

# El gráfico se dibuja en este lienzo y después el CSS lo escala al ancho
# disponible. Las medidas son las del sistema de diseño: marcas finas, punta
# redondeada de 4, separación de 2 entre segmentos apilados.
ANCHO = 720
ALTO = 260
MARGEN_IZQUIERDO = 38
MARGEN_DERECHO = 12
MARGEN_SUPERIOR = 18
MARGEN_INFERIOR = 30
RADIO = 4
SEPARACION = 2


@dataclass
class Segmento:
    x: float
    y: float
    ancho: float
    alto: float
    ruta: str
    valor: int
    serie: str


@dataclass
class Columna:
    etiqueta: str
    titulo: str
    total: int
    x_centro: float
    segmentos: list
    destacada: bool = False
    y_total: float = 0.0


def _techo_lindo(maximo: int) -> int:
    """Un tope redondo para el eje: 0, 5, 10, 20, 50…"""
    if maximo <= 0:
        return 1
    for paso in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        if maximo <= paso * 4:
            return paso * 4
    return maximo


def _ruta_con_punta_redonda(x: float, y: float, ancho: float, alto: float, redondear: bool) -> str:
    """Una barra: la punta del dato va redondeada, la base apoya recta."""
    if alto <= 0:
        return ""
    radio = min(RADIO, ancho / 2, alto)
    if not redondear or radio <= 0:
        return f"M{x},{y} h{ancho} v{alto} h{-ancho} Z"
    return (
        f"M{x},{y + radio} "
        f"a{radio},{radio} 0 0 1 {radio},{-radio} "
        f"h{ancho - 2 * radio} "
        f"a{radio},{radio} 0 0 1 {radio},{radio} "
        f"v{alto - radio} h{-ancho} Z"
    )


def barras_apiladas(datos: list[dict], series: list[str]) -> dict:
    """Arma un gráfico de barras apiladas listo para dibujar.

    ``datos`` es una lista de ``{"etiqueta", "titulo", "valores": {serie: n}}``,
    en el orden en que van a aparecer.
    """
    if not datos:
        return {"columnas": [], "lineas": [], "alto": ALTO, "ancho": ANCHO}

    totales = [sum(fila["valores"].values()) for fila in datos]
    techo = _techo_lindo(max(totales))
    alto_util = ALTO - MARGEN_SUPERIOR - MARGEN_INFERIOR
    ancho_util = ANCHO - MARGEN_IZQUIERDO - MARGEN_DERECHO
    paso = ancho_util / len(datos)
    ancho_barra = min(46, paso * 0.62)
    base = MARGEN_SUPERIOR + alto_util
    mayor = max(totales)

    columnas = []
    for indice, fila in enumerate(datos):
        x = MARGEN_IZQUIERDO + paso * indice + (paso - ancho_barra) / 2
        total = totales[indice]
        y = base
        segmentos = []
        # Se apila de abajo hacia arriba en el orden de las series; la última
        # queda arriba, que es donde el ojo va primero.
        for numero, serie in enumerate(series):
            valor = fila["valores"].get(serie, 0)
            if not valor:
                continue
            alto = valor / techo * alto_util
            hueco = SEPARACION if numero and segmentos else 0
            alto_dibujado = max(alto - hueco, 0.5)
            y -= alto
            es_la_punta = all(not fila["valores"].get(otra) for otra in series[numero + 1 :])
            segmentos.append(
                Segmento(
                    x=x,
                    y=y,
                    ancho=ancho_barra,
                    alto=alto_dibujado,
                    ruta=_ruta_con_punta_redonda(x, y, ancho_barra, alto_dibujado, es_la_punta),
                    valor=valor,
                    serie=serie,
                )
            )
        columnas.append(
            Columna(
                etiqueta=fila["etiqueta"],
                titulo=fila["titulo"],
                total=total,
                x_centro=x + ancho_barra / 2,
                segmentos=segmentos,
                # Se rotula solo lo que hay que leer sí o sí: el mes más alto
                # y el último. Un número sobre cada barra es ruido.
                destacada=total > 0 and (total == mayor or indice == len(datos) - 1),
                y_total=base - (total / techo * alto_util) - 6,
            )
        )

    lineas = []
    for parte in range(5):
        valor = techo * parte / 4
        lineas.append({"y": base - (valor / techo * alto_util), "valor": int(valor)})

    return {
        "columnas": columnas,
        "lineas": lineas,
        "base": base,
        "alto": ALTO,
        "ancho": ANCHO,
        "izquierda": MARGEN_IZQUIERDO,
        "derecha": ANCHO - MARGEN_DERECHO,
    }
