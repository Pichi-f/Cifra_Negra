from modulos.base_datos import inicializar_base_datos
from modulos.visualizacion import app, generar_mapa

if __name__ == '__main__':
    inicializar_base_datos()
    generar_mapa()

    print("\n" + "=" * 50)
    print("Cifra Negra GTM - Servidor iniciado")
    print("Abre tu navegador en: http://localhost:5000")
    print("=" * 50 + "\n")

    app.run(debug=False, port=5000)
