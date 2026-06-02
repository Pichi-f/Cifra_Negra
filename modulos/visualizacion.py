import json
import logging
import os
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from modulos.base_datos import obtener_indicios_para_mapa, inicializar_base_datos
from modulos.extraccion import ejecutar_extraccion
from modulos.procesamiento import ejecutar_pipeline

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)

LOG_PATH = os.path.join('logs', 'bitacora.log')
MAPA_TEMP = os.path.join('templates', 'mapa_folium_temp.html')
GUATEMALA_GEOJSON_PATH = os.path.join('config', 'guatemala_adm1.geojson')

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def _cargar_geojson_guatemala():
    if not os.path.exists(GUATEMALA_GEOJSON_PATH):
        logging.warning("GeoJSON de Guatemala no encontrado: %s", GUATEMALA_GEOJSON_PATH)
        return None

    with open(GUATEMALA_GEOJSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if data.get('type') == 'FeatureCollection':
        return data['features'][0]['geometry']

    if data.get('type') == 'Feature':
        return data['geometry']

    return data


def _punto_en_anillo(lon, lat, anillo):
    dentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi = anillo[i]
        xj, yj = anillo[j]
        cruza = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
        )
        if cruza:
            dentro = not dentro
        j = i
    return dentro


def _punto_en_poligono(lon, lat, poligono):
    if not poligono:
        return False

    exterior = poligono[0]
    if not _punto_en_anillo(lon, lat, exterior):
        return False

    for hueco in poligono[1:]:
        if _punto_en_anillo(lon, lat, hueco):
            return False

    return True


def _punto_en_geometria(lon, lat, geometria):
    if not geometria:
        return True

    tipo = geometria.get('type')
    coords = geometria.get('coordinates', [])

    if tipo == 'Polygon':
        return _punto_en_poligono(lon, lat, coords)

    if tipo == 'MultiPolygon':
        return any(_punto_en_poligono(lon, lat, p) for p in coords)

    return True


def _obtener_bounds(geometria):
    min_lon = 180.0
    max_lon = -180.0
    min_lat = 90.0
    max_lat = -90.0

    def actualizar(lon, lat):
        nonlocal min_lon, max_lon, min_lat, max_lat
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)
        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)

    tipo = geometria.get('type')
    coords = geometria.get('coordinates', [])

    if tipo == 'Polygon':
        for anillo in coords:
            for lon, lat in anillo:
                actualizar(lon, lat)
    elif tipo == 'MultiPolygon':
        for poligono in coords:
            for anillo in poligono:
                for lon, lat in anillo:
                    actualizar(lon, lat)

    return min_lat, max_lat, min_lon, max_lon


def _crear_mascara(geometria):
    if not geometria:
        return None

    min_lat, max_lat, min_lon, max_lon = _obtener_bounds(geometria)
    margen = 1.0
    outer = [
        [min_lon - margen, min_lat - margen],
        [min_lon - margen, max_lat + margen],
        [max_lon + margen, max_lat + margen],
        [max_lon + margen, min_lat - margen],
        [min_lon - margen, min_lat - margen]
    ]

    holes = []
    if geometria.get('type') == 'Polygon':
        holes.append(geometria['coordinates'][0])
    elif geometria.get('type') == 'MultiPolygon':
        for poligono in geometria['coordinates']:
            holes.append(poligono[0])

    return {
        'type': 'Polygon',
        'coordinates': [outer] + holes
    }


def _filtrar_guatemala(indicios, geometria):
    """Filtra indicios dentro del departamento de Guatemala."""
    return [
        i for i in indicios
        if _punto_en_geometria(i['longitud'], i['latitud'], geometria)
    ]


def generar_mapa(categoria=None, fecha_inicio=None, fecha_fin=None):
    """Genera el mapa de calor HTML con los filtros indicados."""
    import folium
    from folium.plugins import HeatMap

    indicios = obtener_indicios_para_mapa(
        categoria=categoria,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )

    geometria = _cargar_geojson_guatemala()
    indicios = _filtrar_guatemala(indicios, geometria)

    mapa = folium.Map(location=[14.6349, -90.5069], zoom_start=12, max_bounds=True)
    datos_calor = [
        [i['latitud'], i['longitud'], i['score_clasificacion']]
        for i in indicios
    ]

    if datos_calor:
        HeatMap(
            datos_calor,
            radius=25,
            blur=15,
            gradient={
                0.2: 'blue',
                0.4: 'lime',
                0.6: 'yellow',
                0.8: 'orange',
                1.0: 'red'
            }
        ).add_to(mapa)

    if geometria:
        min_lat, max_lat, min_lon, max_lon = _obtener_bounds(geometria)
        mapa.fit_bounds([
            [min_lat, min_lon],
            [max_lat, max_lon]
        ])

        mascara = _crear_mascara(geometria)
        if mascara:
            folium.GeoJson(
                mascara,
                style_function=lambda _: {
                    'fillColor': '#ffffff',
                    'color': '#ffffff',
                    'weight': 0,
                    'fillOpacity': 0.85
                }
            ).add_to(mapa)

        folium.GeoJson(
            {'type': 'Feature', 'geometry': geometria, 'properties': {}},
            style_function=lambda _: {
                'color': '#111111',
                'weight': 2,
                'fillOpacity': 0
            }
        ).add_to(mapa)

    mapa.save(MAPA_TEMP)
    return MAPA_TEMP


def obtener_estadisticas(categoria=None, fecha_inicio=None, fecha_fin=None):
    """Retorna estadísticas agregadas para el panel lateral."""
    indicios = obtener_indicios_para_mapa(
        categoria=categoria,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )

    geometria = _cargar_geojson_guatemala()
    indicios = _filtrar_guatemala(indicios, geometria)

    categorias = {'robo': 0, 'extorsion': 0, 'agresion': 0, 'otro': 0}
    for indicio in indicios:
        categoria_delito = indicio['categoria_delito']
        if categoria_delito in categorias:
            categorias[categoria_delito] += 1

    return {
        'total': len(indicios),
        'categorias': categorias,
        'ultima_actualizacion': datetime.now().strftime('%Y-%m-%d %H:%M')
    }


@app.route('/')
def index():
    """Página principal con el mapa de calor."""
    return render_template('mapa.html')


@app.route('/mapa_folium')
def mapa_folium():
    """Genera y retorna el mapa de calor con filtros opcionales."""
    categoria = request.args.getlist('categoria') or None
    fecha_inicio = request.args.get('fecha_inicio') or None
    fecha_fin = request.args.get('fecha_fin') or None

    if categoria and len(categoria) == 1:
        categoria = categoria[0]

    generar_mapa(
        categoria=categoria,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )

    if os.path.exists(MAPA_TEMP):
        with open(MAPA_TEMP, 'r', encoding='utf-8') as fm:
            return Response(fm.read(), mimetype='text/html')

    return Response("<h3>Mapa no disponible</h3>", mimetype='text/html')


@app.route('/estadisticas')
def estadisticas():
    """Retorna estadísticas en JSON para el panel lateral."""
    categoria = request.args.getlist('categoria') or None
    fecha_inicio = request.args.get('fecha_inicio') or None
    fecha_fin = request.args.get('fecha_fin') or None

    if categoria and len(categoria) == 1:
        categoria = categoria[0]

    return jsonify(
        obtener_estadisticas(
            categoria=categoria,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
    )


@app.route('/ejecutar_extraccion', methods=['POST'])
def run_extraccion():
    """Endpoint para disparar el módulo de extracción."""
    resultado = ejecutar_extraccion()
    return jsonify(resultado)


@app.route('/ejecutar_pipeline', methods=['POST'])
def run_pipeline():
    """Endpoint para disparar el pipeline de PLN."""
    resultado = ejecutar_pipeline()
    return jsonify(resultado)


if __name__ == '__main__':
    inicializar_base_datos()
    generar_mapa()

    print("\n" + "=" * 50)
    print("Cifra Negra GTM - Servidor iniciado")
    print("Abre tu navegador en: http://localhost:5000")
    print("=" * 50 + "\n")

    app.run(debug=False, port=5000)