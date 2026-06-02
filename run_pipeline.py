from modulos.procesamiento import ejecutar_pipeline, entrenar_clasificador

if __name__ == '__main__':
    print('>>> Entrenando o cargando clasificador si es necesario...')
    try:
        clasificador, precision = entrenar_clasificador()
        print('>>> Clasificador entrenado/cargado. Precision:', precision)
    except Exception as e:
        print('>>> No se entrenó clasificador:', e)

    print('>>> Ejecutando pipeline de procesamiento...')
    resultado = ejecutar_pipeline()
    print('>>> Resultado pipeline:', resultado)
