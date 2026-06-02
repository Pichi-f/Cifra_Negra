import json
import logging
import os
import re
import string

import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
import pickle
import numpy as np

from modulos.base_datos import (obtener_reportes_sin_procesar,
                                 insertar_indicio_procesado)


def asegurar_recursos_nltk():
    """Descarga recursos NLTK mínimos si faltan en el entorno."""
    recursos = [
        ('tokenizers/punkt', 'punkt'),
        ('corpora/stopwords', 'stopwords'),
        ('corpora/wordnet', 'wordnet'),
        ('corpora/omw-1.4', 'omw-1.4'),
    ]
    for ruta, nombre in recursos:
        try:
            nltk.data.find(ruta)
        except LookupError:
            nltk.download(nombre, quiet=True)

# ---------------------------------------------------------------
# Logging
# ---------------------------------------------------------------
LOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'bitacora.log')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------
CHAPINISMOS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'chapinismos.json'
)
MODELO_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'modelos', 'clasificador.pkl'
)

# ---------------------------------------------------------------
# Referencias geográficas del AMG
# ---------------------------------------------------------------
REFERENCIAS_GEOGRAFICAS = {
    'zona 1': (14.6407, -90.5133),
    'zona 2': (14.6469, -90.5058),
    'zona 3': (14.6418, -90.4981),
    'zona 4': (14.6334, -90.5133),
    'zona 5': (14.6251, -90.5058),
    'zona 6': (14.6520, -90.4953),
    'zona 7': (14.6334, -90.5311),
    'zona 8': (14.6251, -90.5236),
    'zona 9': (14.6176, -90.5160),
    'zona 10': (14.6093, -90.5085),
    'zona 11': (14.6176, -90.5311),
    'zona 12': (14.6010, -90.5160),
    'zona 13': (14.5843, -90.5236),
    'zona 14': (14.5927, -90.5010),
    'zona 15': (14.5843, -90.4859),
    'zona 16': (14.5760, -90.4708),
    'zona 17': (14.5677, -90.4783),
    'zona 18': (14.6520, -90.4708),
    'zona 19': (14.6427, -90.5385),
    'zona 21': (14.5593, -90.5085),
    'mixco': (14.6308, -90.6072),
    'villa nueva': (14.5253, -90.5869),
    'villa canales': (14.4828, -90.5322),
    'san miguel petapa': (14.4994, -90.5547),
    'amatitlan': (14.4797, -90.6197),
    'santa catarina pinula': (14.5644, -90.4997),
    'chinautla': (14.7003, -90.5003),
    'san jose pinula': (14.5497, -90.4197),
    'palencia': (14.6697, -90.3597),
    'calzada roosevelt': (14.6334, -90.5500),
    'calzada aguilar batres': (14.5760, -90.5311),
    'periférico': (14.6010, -90.5311),
    'carretera al atlantico': (14.6520, -90.4633),
    'carretera a el salvador': (14.5677, -90.4633),
}

# Coordenadas por defecto para Guatemala ciudad
COORDENADAS_DEFAULT = (14.6349, -90.5069)


# ---------------------------------------------------------------
# Cargar recursos
# ---------------------------------------------------------------
def cargar_chapinismos():
    """Carga el diccionario de chapinismos desde configuración."""
    with open(CHAPINISMOS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)['diccionario']


# ---------------------------------------------------------------
# Fase 1: Anonimización
# ---------------------------------------------------------------
def anonimizar_texto(texto):
    """
    Elimina datos personales identificables del texto:
    números de teléfono, URLs, menciones de usuario y correos.
    """
    # Eliminar URLs
    texto = re.sub(r'http\S+|www\S+|https\S+', '', texto, flags=re.MULTILINE)

    # Eliminar menciones de usuario (@usuario)
    texto = re.sub(r'@\w+', '', texto)

    # Eliminar números de teléfono guatemaltecos (8 dígitos, con o sin guiones)
    texto = re.sub(r'\b\d{4}[-\s]?\d{4}\b', '', texto)

    # Eliminar correos electrónicos
    texto = re.sub(r'\S+@\S+', '', texto)

    # Eliminar hashtags manteniendo el texto del hashtag
    texto = re.sub(r'#(\w+)', r'\1', texto)

    # Limpiar espacios múltiples
    texto = re.sub(r'\s+', ' ', texto).strip()

    return texto


# ---------------------------------------------------------------
# Fase 2: Preprocesamiento lingüístico
# ---------------------------------------------------------------
def preprocesar_texto(texto, chapinismos):
    """
    Aplica el flujo completo de preprocesamiento lingüístico:
    minúsculas, eliminación de ruido, tokenización,
    traducción de chapinismos, stopwords y lematización.
    """
    asegurar_recursos_nltk()

    # Convertir a minúsculas
    texto = texto.lower()

    # Eliminar emojis y caracteres no ASCII
    texto = texto.encode('ascii', 'ignore').decode('ascii')

    # Eliminar caracteres especiales y puntuación
    texto = re.sub(r'[^\w\s]', ' ', texto)

    # Eliminar números aislados
    texto = re.sub(r'\b\d+\b', '', texto)

    # Tokenizar
    tokens = word_tokenize(texto, language='spanish')

    # Traducir chapinismos
    tokens = [chapinismos.get(token, token) for token in tokens]

    # Eliminar stopwords en español
    stop_words = set(stopwords.words('spanish'))
    # Agregar stopwords específicas del contexto
    stop_words.update([
        'rt', 'gt', 'via', 'hoy', 'ayer', 'foto', 'video',
        'ver', 'dice', 'dijo', 'segun', 'según'
    ])
    tokens = [t for t in tokens if t not in stop_words and len(t) > 2]

    # Lematizar
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(t) for t in tokens]

    return ' '.join(tokens)


# ---------------------------------------------------------------
# Fase 3: Detección de idioma
# ---------------------------------------------------------------
def es_texto_relevante(texto):
    """
    Verifica si el texto contiene referencias geográficas
    o vocabulario delictivo relevante para Guatemala.
    """
    indicadores = [
        'zona', 'mixco', 'villa nueva', 'guatemala', 'petapa',
        'robo', 'asalto', 'balacera', 'extorsion', 'disparo',
        'asaltaron', 'robaron', 'jalaron', 'encañonaron',
        'sicario', 'tiroteo', 'agresion', 'herido', 'muerto',
        'delincuente', 'pandilla', 'mara', 'policia'
    ]
    texto_lower = texto.lower()
    return any(ind in texto_lower for ind in indicadores)


# ---------------------------------------------------------------
# Corpus de entrenamiento
# ---------------------------------------------------------------
def obtener_corpus_entrenamiento():
    """
    Retorna el corpus de entrenamiento etiquetado manualmente.
    Este corpus es la base para entrenar el clasificador.
    """
    corpus = [
        # Robos
        ("asaltaron transporte publico zona 18 dos hombres motocicleta", "robo"),
        ("robo violento zona 11 jalaron cartera señora", "robo"),
        ("encañonaron conductor zona 7 le quitaron vehiculo", "robo"),
        ("robaron tienda zona 3 mediodía sujetos armados", "robo"),
        ("asalto bus zona 6 pasajeros despojados pertenencias", "robo"),
        ("tumbo motocicleta zona 12 se llevaron celular billetera", "robo"),
        ("ladrón jalón cadena señora zona 4 salió corriendo", "robo"),
        ("robo agresivo zona 1 centro historico turistas afectados", "robo"),
        ("asaltaron repartidor zona 15 le quitaron mercaderia moto", "robo"),
        ("robaron gasolinera villa nueva armados encapuchados", "robo"),
        ("asalto mixco calzada roosevelt sujetos armados moto", "robo"),
        ("robo zona 10 zona viva restaurante clientes afectados", "robo"),
        ("carteristas zona 9 mercado central robaron varios", "robo"),
        ("asaltaron clinica zona 13 se llevaron equipo medico", "robo"),
        ("robo residencial santa catarina pinula vivienda", "robo"),

        # Extorsiones
        ("extorsionaron propietario negocio zona 5 cobro mensual", "extorsion"),
        ("comerciante villa nueva recibio llamada extorsion pago", "extorsion"),
        ("mareros cobrando vacuna negocios zona 18 amenazas muerte", "extorsion"),
        ("extorsion transporte zona 6 pilotos amenazados pandilla", "extorsion"),
        ("negocio mixco cerro por extorsion no pudo pagar cuota", "extorsion"),
        ("llamada extorsion zona 21 amenazaron familia empresario", "extorsion"),
        ("cobro extorsion zona 3 mercado amenaza negocios", "extorsion"),
        ("pandilla cobrando zona 7 negocios amenazados cierre", "extorsion"),
        ("extorsion bus zona 12 pilotos afectados ruta amenazada", "extorsion"),
        ("chivo cobrado villa canales comerciantes afectados", "extorsion"),

        # Agresiones
        ("balacera zona 18 dos heridos enfrentamiento pandillas", "agresion"),
        ("tiroteo mixco colonia zona residencial muertos heridos", "agresion"),
        ("sicario moto disparó hombre zona 6 murió hospital", "agresion"),
        ("pelea callejera zona 1 heridos machete intervinieron", "agresion"),
        ("agresion zona 12 hombre golpeado grupo personas robo", "agresion"),
        ("balacera villa nueva colonia residentes asustados", "agresion"),
        ("disparos zona 18 enfrentamiento pandillas heridos", "agresion"),
        ("ataque sicarios zona 3 vehiculo baleado conductor herido", "agresion"),
        ("riña callejera chinautla heridos traslado hospital", "agresion"),
        ("agresion zona 7 hombre apuñalado robo frustrado", "agresion"),

        # Ruido digital (no delitos)
        ("partido futbol zona 5 estadio lleno aficionados", "otro"),
        ("concierto zona 10 artista internacional entradas agotadas", "otro"),
        ("accidente tránsito zona 4 colisión vehículos sin heridos", "otro"),
        ("manifestación zona 1 marcha pacífica trabajadores", "otro"),
        ("incendio zona 3 bomberos controlaron fuego bodega", "otro"),
        ("accidente moto zona 7 conductor lesionado no grave", "otro"),
        ("feria zona 6 actividades culturales familias asistieron", "otro"),
        ("accidente zona 11 bus pasajeros sin heridos", "otro"),
        ("lluvia inundaciones zona 8 calles afectadas vehículos", "otro"),
        ("protesta zona 1 estudiantes universidad manifestacion", "otro"),
    ]
    return corpus


# ---------------------------------------------------------------
# Entrenamiento del clasificador
# ---------------------------------------------------------------
def entrenar_clasificador():
    """
    Entrena el modelo de clasificación con el corpus de entrenamiento
    y lo guarda en disco para uso posterior.
    """
    logger.info("Iniciando entrenamiento del clasificador...")
    chapinismos = cargar_chapinismos()
    corpus = obtener_corpus_entrenamiento()

    textos = []
    etiquetas = []

    for texto, etiqueta in corpus:
        texto_anonimizado = anonimizar_texto(texto)
        texto_procesado = preprocesar_texto(texto_anonimizado, chapinismos)
        textos.append(texto_procesado)
        etiquetas.append(etiqueta)

    # Pipeline: TF-IDF + Naive Bayes
    clasificador = Pipeline([
        ('tfidf', TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            max_features=5000
        )),
        ('clf', MultinomialNB(alpha=0.1))
    ])

    # Validación cruzada
    scores = cross_val_score(clasificador, textos, etiquetas, cv=5)
    precision_promedio = scores.mean()
    logger.info(
        f"Precisión promedio (validación cruzada): {precision_promedio:.2%}"
    )
    print(f"Precisión del clasificador: {precision_promedio:.2%}")

    # Entrenar con todo el corpus
    clasificador.fit(textos, etiquetas)

    # Guardar modelo
    with open(MODELO_PATH, 'wb') as f:
        pickle.dump(clasificador, f)

    logger.info(f"Clasificador guardado en {MODELO_PATH}")
    return clasificador, precision_promedio


def cargar_clasificador():
    """Carga el clasificador desde disco o lo entrena si no existe."""
    if os.path.exists(MODELO_PATH):
        with open(MODELO_PATH, 'rb') as f:
            return pickle.load(f)
    else:
        clasificador, _ = entrenar_clasificador()
        return clasificador


# ---------------------------------------------------------------
# Geocodificación
# ---------------------------------------------------------------
def obtener_coordenadas(texto_original):
    """
    Extrae coordenadas geográficas del texto.
    Primero busca referencias conocidas del AMG,
    luego intenta geocodificación con Nominatim.
    """
    texto_lower = texto_original.lower()

    # Buscar referencias geográficas conocidas
    for referencia, coordenadas in REFERENCIAS_GEOGRAFICAS.items():
        if referencia in texto_lower:
            return coordenadas

    # Intentar geocodificación con Nominatim
    try:
        geolocator = Nominatim(user_agent="cifra_negra_gtm")
        patrones = [
            r'zona\s+(\d+)',
            r'colonia\s+([\w\s]+)',
            r'barrio\s+([\w\s]+)',
        ]
        for patron in patrones:
            match = re.search(patron, texto_lower)
            if match:
                termino = match.group(0) + ' Guatemala City'
                location = geolocator.geocode(termino, timeout=5)
                if location:
                    return (location.latitude, location.longitude)
                time.sleep(1)
    except GeocoderTimedOut:
        logger.warning("Timeout en geocodificación, usando coordenadas default.")
    except Exception as e:
        logger.warning(f"Error en geocodificación: {str(e)}")

    # Retornar coordenadas del centro de Guatemala ciudad por defecto
    return COORDENADAS_DEFAULT


# ---------------------------------------------------------------
# Pipeline principal de procesamiento
# ---------------------------------------------------------------
def ejecutar_pipeline():
    """
    Ejecuta el pipeline completo de PLN sobre todos los
    reportes crudos pendientes de procesar.
    """
    logger.info("=" * 60)
    logger.info("INICIO DEL PIPELINE DE PLN")

    chapinismos = cargar_chapinismos()
    clasificador = cargar_clasificador()

    reportes = obtener_reportes_sin_procesar()
    logger.info(f"Reportes pendientes de procesar: {len(reportes)}")
    print(f"\nReportes a procesar: {len(reportes)}")

    total_procesados = 0
    total_validos = 0
    total_descartados = 0
    total_errores = 0

    for reporte in reportes:
        try:
            id_reporte = reporte['id_reporte']
            texto_crudo = reporte['texto_crudo']
            fecha_publicacion = reporte['fecha_publicacion']

            # Verificar relevancia básica antes de procesar
            if not es_texto_relevante(texto_crudo):
                logger.info(
                    f"Reporte {id_reporte} descartado: sin relevancia geográfica."
                )
                total_descartados += 1
                total_procesados += 1
                continue

            # Fase 1: Anonimización
            texto_anonimizado = anonimizar_texto(texto_crudo)

            # Fase 2: Preprocesamiento lingüístico
            texto_procesado = preprocesar_texto(texto_anonimizado, chapinismos)

            if not texto_procesado or len(texto_procesado.split()) < 3:
                logger.info(
                    f"Reporte {id_reporte} descartado: texto insuficiente."
                )
                total_descartados += 1
                total_procesados += 1
                continue

            # Fase 3: Clasificación
            categoria = clasificador.predict([texto_procesado])[0]
            probabilidades = clasificador.predict_proba([texto_procesado])[0]
            score = float(max(probabilidades))

            # Umbral de confianza mínimo
            UMBRAL = 0.55
            if score < UMBRAL:
                logger.info(
                    f"Reporte {id_reporte} descartado: "
                    f"score {score:.2f} bajo umbral {UMBRAL}."
                )
                total_descartados += 1
                total_procesados += 1
                continue

            # Descartar si clasificó como "otro" con alta confianza
            if categoria == 'otro' and score > 0.70:
                logger.info(
                    f"Reporte {id_reporte} descartado como ruido digital."
                )
                total_descartados += 1
                total_procesados += 1
                continue

            # Fase 4: Geocodificación
            latitud, longitud = obtener_coordenadas(texto_crudo)

            # Insertar indicio procesado
            insertar_indicio_procesado(
                id_reporte=id_reporte,
                texto_procesado=texto_procesado,
                categoria_delito=categoria,
                score_clasificacion=score,
                latitud=latitud,
                longitud=longitud,
                fecha_publicacion=fecha_publicacion
            )

            total_validos += 1
            total_procesados += 1
            logger.info(
                f"Reporte {id_reporte} procesado: "
                f"categoria={categoria}, score={score:.2f}, "
                f"lat={latitud:.4f}, lon={longitud:.4f}"
            )

        except Exception as e:
            logger.error(f"Error procesando reporte {id_reporte}: {str(e)}")
            total_errores += 1
            total_procesados += 1
            continue

    logger.info("FIN DEL PIPELINE DE PLN")
    logger.info(f"Procesados:   {total_procesados}")
    logger.info(f"Válidos:      {total_validos}")
    logger.info(f"Descartados:  {total_descartados}")
    logger.info(f"Errores:      {total_errores}")
    logger.info("=" * 60)

    print(f"\nPipeline completado:")
    print(f"  Procesados:   {total_procesados}")
    print(f"  Válidos:      {total_validos}")
    print(f"  Descartados:  {total_descartados}")
    print(f"  Errores:      {total_errores}")

    return {
        'procesados': total_procesados,
        'validos': total_validos,
        'descartados': total_descartados,
        'errores': total_errores
    }