import sqlite3
import os
import logging

# Ruta de la base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cifra_negra.db')

def obtener_conexion():
    """Retorna una conexión a la base de datos SQLite."""
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    return conexion

def inicializar_base_datos():
    """Crea las tablas si no existen."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reporte_crudo (
            id_reporte INTEGER PRIMARY KEY AUTOINCREMENT,
            id_publicacion_plataforma TEXT UNIQUE NOT NULL,
            plataforma TEXT NOT NULL,
            texto_crudo TEXT NOT NULL,
            url_publicacion TEXT,
            fecha_publicacion DATETIME NOT NULL,
            fecha_extraccion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS indicio_procesado (
            id_indicio INTEGER PRIMARY KEY AUTOINCREMENT,
            id_reporte INTEGER NOT NULL,
            texto_procesado TEXT NOT NULL,
            categoria_delito TEXT NOT NULL,
            score_clasificacion REAL NOT NULL,
            latitud REAL NOT NULL,
            longitud REAL NOT NULL,
            fecha_publicacion DATETIME NOT NULL,
            FOREIGN KEY (id_reporte) REFERENCES reporte_crudo(id_reporte)
        )
    ''')

    conexion.commit()
    conexion.close()
    logging.info("Base de datos inicializada correctamente.")

def existe_publicacion(id_publicacion_plataforma):
    """Verifica si una publicación ya existe en la base de datos."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id_reporte FROM reporte_crudo WHERE id_publicacion_plataforma = ?",
        (id_publicacion_plataforma,)
    )
    resultado = cursor.fetchone()
    conexion.close()
    return resultado is not None

def insertar_reporte_crudo(id_publicacion_plataforma, plataforma, texto_crudo,
                            url_publicacion, fecha_publicacion):
    """Inserta un nuevo reporte crudo en la base de datos."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute('''
            INSERT INTO reporte_crudo 
            (id_publicacion_plataforma, plataforma, texto_crudo, url_publicacion, fecha_publicacion)
            VALUES (?, ?, ?, ?, ?)
        ''', (id_publicacion_plataforma, plataforma, texto_crudo,
              url_publicacion, fecha_publicacion))
        conexion.commit()
        id_insertado = cursor.lastrowid
        return id_insertado
    except sqlite3.IntegrityError:
        logging.warning(f"Publicación duplicada ignorada: {id_publicacion_plataforma}")
        return None
    finally:
        conexion.close()

def insertar_indicio_procesado(id_reporte, texto_procesado, categoria_delito,
                                score_clasificacion, latitud, longitud, fecha_publicacion):
    """Inserta un indicio procesado en la base de datos."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute('''
        INSERT INTO indicio_procesado
        (id_reporte, texto_procesado, categoria_delito, score_clasificacion,
         latitud, longitud, fecha_publicacion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (id_reporte, texto_procesado, categoria_delito, score_clasificacion,
          latitud, longitud, fecha_publicacion))
    conexion.commit()
    conexion.close()

def obtener_reportes_sin_procesar():
    """Retorna todos los reportes crudos que aún no tienen indicio procesado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT rc.* FROM reporte_crudo rc
        LEFT JOIN indicio_procesado ip ON rc.id_reporte = ip.id_reporte
        WHERE ip.id_reporte IS NULL
    ''')
    resultados = cursor.fetchall()
    conexion.close()
    return resultados

def obtener_indicios_para_mapa(categoria=None, fecha_inicio=None, fecha_fin=None):
    """Retorna los indicios procesados con filtros opcionales para el mapa."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    query = "SELECT * FROM indicio_procesado WHERE 1=1"
    parametros = []

    if categoria:
        if isinstance(categoria, (list, tuple)):
            placeholders = ",".join(["?"] * len(categoria))
            query += f" AND categoria_delito IN ({placeholders})"
            parametros.extend(categoria)
        else:
            query += " AND categoria_delito = ?"
            parametros.append(categoria)
    if fecha_inicio:
        query += " AND fecha_publicacion >= ?"
        parametros.append(fecha_inicio)
    if fecha_fin:
        query += " AND fecha_publicacion <= ?"
        parametros.append(fecha_fin)

    cursor.execute(query, parametros)
    resultados = cursor.fetchall()
    conexion.close()
    return resultados