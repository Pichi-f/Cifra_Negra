from modulos.procesamiento import entrenar_clasificador, ejecutar_pipeline

if __name__ == "__main__":
    print("Paso 1: Entrenando clasificador...")
    clasificador, precision = entrenar_clasificador()
    print(f"Clasificador entrenado con precision: {precision:.2%}")

    print("\nPaso 2: Ejecutando pipeline de PLN...")
    ejecutar_pipeline()