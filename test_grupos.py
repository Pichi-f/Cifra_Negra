from modulos.extraccion import (
    inicializar_driver, cargar_cookies_facebook,
    cargar_grupos_facebook, extraer_de_grupo_facebook,
    existe_publicacion
)
from modulos.base_datos import inicializar_base_datos, insertar_reporte_crudo
import time
import random

inicializar_base_datos()
grupos = cargar_grupos_facebook()
grupos = grupos[:1]
driver = inicializar_driver(headless=True)
cargar_cookies_facebook(driver)
time.sleep(3)

total = 0
for url in grupos:
    print(f"\nProcesando: {url}")
    pubs = extraer_de_grupo_facebook(driver, url)
    print(f"Encontradas: {len(pubs)}")
    for pub in pubs:
        if not existe_publicacion(pub['id']):
            insertar_reporte_crudo(
                id_publicacion_plataforma=pub['id'],
                plataforma=pub['plataforma'],
                texto_crudo=pub['texto'],
                url_publicacion=pub['url'],
                fecha_publicacion=pub['fecha']
            )
            total += 1
    time.sleep(random.uniform(10, 15))

driver.quit()
print(f"\nTotal nuevos capturados: {total}")