import hashlib
import json
import logging
import os
import pickle
import random
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from modulos.base_datos import (existe_publicacion, inicializar_base_datos,
                                 insertar_reporte_crudo)

# ---------------------------------------------------------------
# Logging
# ---------------------------------------------------------------
LOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'bitacora.log')
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)

CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'palabras_clave.json'
)
COOKIES_X_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'cookies_x.pkl'
)
COOKIES_FB_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'cookies_facebook.pkl'
)

PERFIL_CHROME = os.path.expanduser('~') + r'\AppData\Local\Google\Chrome\User Data'
PERFIL_NOMBRE = 'Profile 1'

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


def generar_id_estable(*componentes):
    """Genera un identificador estable para deduplicación entre ejecuciones."""
    texto_base = '||'.join(str(componente).strip().lower() for componente in componentes)
    return hashlib.sha256(texto_base.encode('utf-8')).hexdigest()[:24]


def obtener_servicio_chromedriver():
    """Resuelve el ejecutable de ChromeDriver sin depender de una ruta fija."""
    try:
        return Service(ChromeDriverManager().install())
    except Exception:
        chromedriver_path = os.path.expanduser('~') + \
        r'\.wdm\drivers\chromedriver\win64\148.0.7778.178\chromedriver-win64\chromedriver.exe'
        return Service(chromedriver_path)


# ---------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------
def cargar_palabras_clave():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        datos = json.load(f)
    return datos['palabras_clave']


def cargar_grupos_facebook():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        datos = json.load(f)
    return datos.get('grupos_facebook', [])


# ---------------------------------------------------------------
# Driver para extracción (headless, sin perfil)
# ---------------------------------------------------------------
def inicializar_driver(headless=True):
    """Driver para la extracción normal, sin perfil de usuario."""
    opciones = Options()
    opciones.page_load_strategy = 'eager'
    user_agent = random.choice(USER_AGENTS)
    opciones.add_argument(f'user-agent={user_agent}')

    if headless:
        opciones.add_argument('--headless=new')

    opciones.add_argument('--no-sandbox')
    opciones.add_argument('--disable-dev-shm-usage')
    opciones.add_argument('--disable-blink-features=AutomationControlled')
    opciones.add_argument('--disable-infobars')
    opciones.add_argument('--disable-extensions')
    opciones.add_argument('--disable-gpu')
    opciones.add_argument('--window-size=1920,1080')
    opciones.add_argument('--lang=es-GT')
    opciones.add_experimental_option(
        'excludeSwitches', ['enable-automation', 'enable-logging']
    )
    opciones.add_experimental_option('useAutomationExtension', False)
    opciones.add_experimental_option('prefs', {
        'profile.default_content_setting_values.notifications': 2,
        'credentials_enable_service': False,
        'profile.password_manager_enabled': False
    })

    servicio = obtener_servicio_chromedriver()
    driver = webdriver.Chrome(service=servicio, options=opciones)
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(30)
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        'userAgent': user_agent
    })
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]})"
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'languages', "
        "{get: () => ['es-GT', 'es', 'en']})"
    )
    return driver


# ---------------------------------------------------------------
# Driver con perfil real (solo para guardar cookies)
# ---------------------------------------------------------------
def inicializar_driver_con_perfil():
    """Driver que usa tu perfil real de Chrome para el guardado de cookies."""
    opciones = Options()
    opciones.page_load_strategy = 'eager'
    opciones.add_argument(f'--user-data-dir={PERFIL_CHROME}')
    opciones.add_argument(f'--profile-directory={PERFIL_NOMBRE}')
    opciones.add_argument('--no-sandbox')
    opciones.add_argument('--disable-dev-shm-usage')
    opciones.add_argument('--no-first-run')
    opciones.add_argument('--no-default-browser-check')
    opciones.add_argument('--disable-extensions')
    opciones.add_argument('--window-size=1280,800')
    opciones.add_experimental_option(
        'excludeSwitches', ['enable-automation', 'enable-logging']
    )
    opciones.add_experimental_option('useAutomationExtension', False)

    servicio = obtener_servicio_chromedriver()
    driver = webdriver.Chrome(service=servicio, options=opciones)
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(30)
    return driver


# ---------------------------------------------------------------
# Guardar cookies (ejecutar una sola vez)
# ---------------------------------------------------------------
def guardar_cookies_x():
    """
    Abre Chrome con tu perfil real para que hagas login en X.
    Guarda las cookies al presionar ENTER. Solo ejecutar una vez.
    """
    print("\n" + "=" * 50)
    print("GUARDADO DE COOKIES - X (Twitter)")
    print("=" * 50)
    print("Se abrirá Chrome con tu perfil real.")
    print("1. Espera a que cargue el navegador")
    print("2. Inicia sesión en X si no lo has hecho")
    print("3. Cuando veas tu feed, regresa aquí")
    print("4. Presiona ENTER para guardar las cookies")
    print("=" * 50 + "\n")

    driver = inicializar_driver_con_perfil()

    time.sleep(3)
    driver.get('https://x.com/login')
    time.sleep(5)

    input(">>> Presiona ENTER cuando hayas iniciado sesión en X...")

    cookies = driver.get_cookies()
    with open(COOKIES_X_PATH, 'wb') as f:
        pickle.dump(cookies, f)

    print(f"Cookies de X guardadas exitosamente ({len(cookies)} cookies).")
    logging.info(f"Cookies de X guardadas: {len(cookies)} cookies.")
    driver.quit()


def guardar_cookies_facebook():
    """
    Abre Chrome con tu perfil real para que hagas login en Facebook.
    Guarda las cookies al presionar ENTER. Solo ejecutar una vez.
    """
    print("\n" + "=" * 50)
    print("GUARDADO DE COOKIES - Facebook")
    print("=" * 50)
    print("Se abrirá Chrome con tu perfil real.")
    print("1. Espera a que cargue el navegador")
    print("2. Inicia sesión en Facebook si no lo has hecho")
    print("3. Cuando veas tu feed, regresa aquí")
    print("4. Presiona ENTER para guardar las cookies")
    print("=" * 50 + "\n")

    driver = inicializar_driver_con_perfil()

    time.sleep(3)
    driver.get('https://www.facebook.com/')
    time.sleep(5)

    input(">>> Presiona ENTER cuando hayas iniciado sesión en Facebook...")

    cookies = driver.get_cookies()
    with open(COOKIES_FB_PATH, 'wb') as f:
        pickle.dump(cookies, f)

    print(f"Cookies de Facebook guardadas ({len(cookies)} cookies).")
    logging.info(f"Cookies de Facebook guardadas: {len(cookies)} cookies.")
    driver.quit()


# ---------------------------------------------------------------
# Cargar cookies en driver de extracción
# ---------------------------------------------------------------
def cargar_cookies_x(driver):
    """Carga las cookies de X en el driver de extracción."""
    if not os.path.exists(COOKIES_X_PATH):
        logging.error(
            "No se encontraron cookies de X. "
            "Ejecuta guardar_sesiones.py primero."
        )
        return False
    try:
        driver.get('https://x.com')
        time.sleep(2)
        with open(COOKIES_X_PATH, 'rb') as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception:
                continue
        driver.get('https://x.com/home')
        time.sleep(4)

        if 'home' in driver.current_url:
            logging.info("Sesión de X restaurada exitosamente.")
            return True
        else:
            logging.warning(
                f"No se pudo restaurar sesión de X. "
                f"URL actual: {driver.current_url}"
            )
            return False
    except Exception as e:
        logging.error(f"Error cargando cookies de X: {str(e)}")
        return False


def cargar_cookies_facebook(driver):
    """Carga las cookies de Facebook en el driver de extracción."""
    if not os.path.exists(COOKIES_FB_PATH):
        logging.error(
            "No se encontraron cookies de Facebook. "
            "Ejecuta guardar_sesiones.py primero."
        )
        return False
    try:
        driver.get('https://www.facebook.com')
        time.sleep(2)
        with open(COOKIES_FB_PATH, 'rb') as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception:
                continue
        driver.get('https://www.facebook.com')
        time.sleep(4)

        if 'login' not in driver.current_url:
            logging.info("Sesión de Facebook restaurada exitosamente.")
            return True
        else:
            logging.warning(
                f"No se pudo restaurar sesión de Facebook. "
                f"URL actual: {driver.current_url}"
            )
            return False
    except Exception as e:
        logging.error(f"Error cargando cookies de Facebook: {str(e)}")
        return False


# ---------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------
def scroll_humano(driver, veces=4):
    """Scroll gradual para simular comportamiento humano."""
    for _ in range(veces):
        cantidad = random.randint(300, 800)
        driver.execute_script(f"window.scrollBy(0, {cantidad});")
        time.sleep(random.uniform(1.5, 3.5))
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(random.uniform(2, 4))

def scroll_con_cierre_popup(driver, veces=8):
    """
    Hace scroll gradual eliminando popups y overlays de Facebook.
    """
    for i in range(veces):
        try:
            # Eliminar dialogs, overlays y bloqueos del DOM
            driver.execute_script("""
                // Cerrar dialogs
                document.querySelectorAll('[role="dialog"]').forEach(
                    function(d) { d.remove(); }
                );

                // Eliminar overlays semitransparentes
                document.querySelectorAll('[data-visualcompletion="ignore-dynamic"]').forEach(
                    function(o) { o.remove(); }
                );

                // Restaurar scroll del body que Facebook bloquea
                document.body.style.overflow = 'auto';
                document.body.style.position = 'static';
                document.documentElement.style.overflow = 'auto';

                // Eliminar cualquier div con position fixed de alta z-index
                document.querySelectorAll('div').forEach(function(d) {
                    var style = window.getComputedStyle(d);
                    if (style.position === 'fixed' && 
                        parseInt(style.zIndex) > 100 &&
                        style.backgroundColor.includes('rgba')) {
                        d.remove();
                    }
                });
            """)
            time.sleep(0.8)

        except Exception:
            pass

        cantidad = random.randint(400, 900)
        driver.execute_script(f"window.scrollBy(0, {cantidad});")
        time.sleep(random.uniform(2, 4))

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(random.uniform(2, 3))


def detectar_captcha(driver):
    """Detecta si hay CAPTCHA real en la página actual."""
    indicadores_fuertes = [
        'recaptcha',
        'verify you are human',
        'cf-challenge',
        'challenge-form',
        'captcha-delivery'
    ]
    contenido = driver.page_source.lower()

    # Solo contar como CAPTCHA si hay indicadores fuertes
    return any(i in contenido for i in indicadores_fuertes)


# ---------------------------------------------------------------
# Extracción en X
# ---------------------------------------------------------------
def extraer_de_x(driver, palabra_clave):
    """Extrae publicaciones de X usando sesión activa por cookies."""
    publicaciones = []
    try:
        termino = palabra_clave.replace(' ', '%20')
        url = (
            f"https://x.com/search?q={termino}"
            f"%20lang%3Aes&src=typed_query&f=live"
        )
        driver.get(url)
        time.sleep(random.uniform(3, 6))

        if detectar_captcha(driver):
            logging.warning(f"CAPTCHA en X para '{palabra_clave}'.")
            return publicaciones

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
                )
            )
        except Exception:
            logging.warning(f"Sin resultados en X para: '{palabra_clave}'")
            return publicaciones

        scroll_humano(driver, veces=4)
        tweets = driver.find_elements(
            By.CSS_SELECTOR, 'article[data-testid="tweet"]'
        )
        logging.info(f"X: {len(tweets)} tweets para '{palabra_clave}'")

        for tweet in tweets:
            try:
                try:
                    texto = tweet.find_element(
                        By.CSS_SELECTOR, 'div[data-testid="tweetText"]'
                    ).text
                except Exception:
                    continue

                if not texto or len(texto) < 10:
                    continue

                try:
                    fecha_raw = tweet.find_element(
                        By.TAG_NAME, 'time'
                    ).get_attribute('datetime')
                    fecha = datetime.fromisoformat(
                        fecha_raw.replace('Z', '+00:00')
                    ).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                try:
                    enlace = tweet.find_element(
                        By.CSS_SELECTOR, 'a[href*="/status/"]'
                    )
                    url_pub = enlace.get_attribute('href')
                    id_pub = url_pub.split('/status/')[-1].split('?')[0]
                except Exception:
                    url_pub = None
                    id_pub = f"x_{generar_id_estable('x', texto)}"

                publicaciones.append({
                    'id': id_pub,
                    'plataforma': 'X',
                    'texto': texto,
                    'url': url_pub,
                    'fecha': fecha
                })

            except Exception as e:
                logging.error(f"Error en tweet: {str(e)}")
                continue

    except Exception as e:
        logging.error(f"Error general X '{palabra_clave}': {str(e)}")

    return publicaciones


# ---------------------------------------------------------------
# Extracción en Facebook
# ---------------------------------------------------------------
def extraer_de_facebook(driver, palabra_clave):
    """Extrae publicaciones de Facebook usando sesión activa por cookies."""
    publicaciones = []
    try:
        termino = palabra_clave.replace(' ', '%20')
        url = f"https://www.facebook.com/search/posts?q={termino}"
        driver.get(url)
        time.sleep(random.uniform(4, 7))

        if detectar_captcha(driver):
            logging.warning(f"CAPTCHA en Facebook para '{palabra_clave}'.")
            return publicaciones

        if 'login' in driver.current_url.lower():
            logging.warning("Facebook redirigió a login. Sesión expirada.")
            return publicaciones

        scroll_humano(driver, veces=5)

        selectores = [
            'div[data-ad-comet-preview="message"]',
            'div[data-ad-preview="message"]',
            'div[dir="auto"][class*="x1lliihq"]',
        ]

        posts = []
        for selector in selectores:
            try:
                posts = driver.find_elements(By.CSS_SELECTOR, selector)
                if posts:
                    break
            except Exception:
                continue

        logging.info(f"Facebook: {len(posts)} posts para '{palabra_clave}'")

        for post in posts:
            try:
                texto = post.text
                if not texto or len(texto) < 10:
                    continue
                fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                id_pub = f"fb_{generar_id_estable('facebook', texto)}"
                publicaciones.append({
                    'id': id_pub,
                    'plataforma': 'Facebook',
                    'texto': texto,
                    'url': driver.current_url,
                    'fecha': fecha
                })
            except Exception as e:
                logging.error(f"Error en post Facebook: {str(e)}")
                continue

    except Exception as e:
        logging.error(f"Error general Facebook '{palabra_clave}': {str(e)}")

    return publicaciones


# ---------------------------------------------------------------
# Extracción directa de grupos de Facebook
# ---------------------------------------------------------------
def extraer_de_grupo_facebook(driver, url_grupo):
    """
    Extrae publicaciones de un grupo público de Facebook.
    Estrategia: extraer lo visible inmediatamente antes de que
    aparezca el overlay, luego intentar scroll limpiando el DOM.
    """
    publicaciones = []
    textos_vistos = set()
    inicio = time.time()
    tiempo_maximo = 180

    def limpiar_overlays():
        """Elimina todos los overlays y restaura el scroll."""
        try:
            driver.execute_script("""
                const selectores = [
                    '[role="dialog"]',
                    '[aria-modal="true"]',
                    '[data-visualcompletion="ignore-dynamic"]',
                    'div[style*="position: fixed"]',
                    'div[style*="position:fixed"]',
                    'div[style*="z-index"]'
                ];

                selectores.forEach(function(selector) {
                    document.querySelectorAll(selector).forEach(function(node) {
                        try { node.remove(); } catch (e) {}
                    });
                });

                document.querySelectorAll('div[aria-label="Cerrar"], div[aria-label="Close"], button[aria-label="Cerrar"], button[aria-label="Close"]').forEach(function(b) {
                    try { b.click(); } catch (e) {}
                });

                document.body.style.overflow = 'auto';
                document.body.style.position = 'static';
                document.documentElement.style.overflow = 'auto';
                document.body.style.height = 'auto';
                document.documentElement.style.height = 'auto';
            """)
            time.sleep(0.5)
        except Exception:
            pass

    def hay_overlay_bloqueante():
        """Detecta si Facebook está mostrando una capa que bloquea el scroll."""
        try:
            return bool(driver.execute_script("""
                const dialogos = document.querySelectorAll('[role="dialog"], [aria-modal="true"], [data-visualcompletion="ignore-dynamic"]');
                const bodyOverflow = window.getComputedStyle(document.body).overflow;
                const htmlOverflow = window.getComputedStyle(document.documentElement).overflow;
                const bloqueoScroll = bodyOverflow === 'hidden' || htmlOverflow === 'hidden';
                return dialogos.length > 0 || bloqueoScroll;
            """))
        except Exception:
            return False

    def forzar_scroll(cantidad):
        """Intenta varias estrategias de scroll cuando Facebook bloquea la página."""
        estrategias = [
            lambda: driver.execute_script("window.scrollBy(0, arguments[0]);", cantidad),
            lambda: driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        ]

        for estrategia in estrategias:
            try:
                estrategia()
                time.sleep(random.uniform(1.0, 2.0))
                if not hay_overlay_bloqueante():
                    return True
            except Exception:
                continue

        try:
            body = driver.find_element(By.TAG_NAME, 'body')
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(random.uniform(1.0, 2.0))
            return not hay_overlay_bloqueante()
        except Exception:
            return False

    def excedio_tiempo():
        return (time.time() - inicio) > tiempo_maximo

    def extraer_publicaciones_visibles():
        """Extrae todas las publicaciones actualmente visibles."""
        encontradas = []
        selectores = [
            'div[data-ad-comet-preview="message"]',
            'div[data-ad-preview="message"]',
            'div[role="article"] div[dir="auto"]',
        ]
        for selector in selectores:
            try:
                elementos = driver.find_elements(By.CSS_SELECTOR, selector)
                if elementos:
                    for elem in elementos:
                        try:
                            texto = elem.text.strip()
                            if texto and len(texto) >= 15 and texto not in textos_vistos:
                                textos_vistos.add(texto)
                                encontradas.append(texto)
                        except Exception:
                            continue
                    if encontradas:
                        break
            except Exception:
                continue
        return encontradas

    try:
        try:
            driver.get(url_grupo)
        except TimeoutException:
            logging.warning(f"Timeout cargando grupo {url_grupo}; continuando con la página parcial.")
            try:
                driver.execute_script('window.stop();')
            except Exception:
                pass
        time.sleep(random.uniform(4, 6))

        if 'login' in driver.current_url.lower():
            logging.warning(f"Facebook redirigió a login: {url_grupo}")
            return publicaciones

        # Cerrar popup inicial
        limpiar_overlays()
        try:
            driver.execute_script("""
                document.querySelectorAll(
                    '[aria-label="Cerrar"], [aria-label="Close"]'
                ).forEach(function(b) { b.click(); });
            """)
            time.sleep(1)
        except Exception:
            pass
        limpiar_overlays()

        # Si Facebook deja una capa opaca bloqueando el scroll, insistir un poco.
        for _ in range(3):
            if excedio_tiempo():
                logging.warning(f"Tiempo máximo alcanzado antes de iniciar scroll en grupo {url_grupo}.")
                break
            if not hay_overlay_bloqueante():
                break
            limpiar_overlays()
            try:
                body = driver.find_element(By.TAG_NAME, 'body')
                body.send_keys(Keys.ESCAPE)
            except Exception:
                pass
            time.sleep(0.8)

        # Extraer publicaciones iniciales inmediatamente
        textos_iniciales = extraer_publicaciones_visibles()
        logging.info(
            f"Grupo {url_grupo}: {len(textos_iniciales)} "
            f"publicaciones iniciales"
        )

        # Intentar 5 rondas de scroll con limpieza
        for ronda in range(6):
            if excedio_tiempo():
                logging.warning(f"Tiempo máximo alcanzado en grupo {url_grupo}; deteniendo extracción.")
                break
            limpiar_overlays()

            # Scroll gradual
            avanzó = False
            for _ in range(4):
                if excedio_tiempo():
                    break
                limpiar_overlays()
                cantidad = random.randint(400, 800)
                avanzó = forzar_scroll(cantidad) or avanzó
                time.sleep(random.uniform(1.2, 2.2))
                limpiar_overlays()

                if hay_overlay_bloqueante():
                    try:
                        body = driver.find_element(By.TAG_NAME, 'body')
                        body.send_keys(Keys.ESCAPE)
                    except Exception:
                        pass
                    limpiar_overlays()

            # Extraer nuevas publicaciones después del scroll
            nuevas = extraer_publicaciones_visibles()
            if nuevas:
                logging.info(
                    f"Ronda {ronda+1}: {len(nuevas)} nuevas publicaciones"
                )
            elif not avanzó:
                logging.info(
                    f"Ronda {ronda+1}: scroll bloqueado o sin avance visible"
                )

            time.sleep(random.uniform(1, 2))

        # Convertir todos los textos a publicaciones
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for texto in textos_vistos:
            id_pub = f"fb_grupo_{generar_id_estable('facebook_grupo', url_grupo, texto)}"
            publicaciones.append({
                'id': id_pub,
                'plataforma': 'Facebook',
                'texto': texto,
                'url': url_grupo,
                'fecha': fecha
            })

        logging.info(
            f"Total extraído del grupo {url_grupo}: "
            f"{len(publicaciones)} publicaciones"
        )

    except Exception as e:
        logging.error(f"Error en grupo {url_grupo}: {str(e)}")

    return publicaciones


# ---------------------------------------------------------------
# Proceso principal de extracción
# ---------------------------------------------------------------
def extraer_publicaciones(palabras_clave):
    """Ejecuta extracción completa sobre X y Facebook con cookies."""
    inicializar_base_datos()

    total_capturados = 0
    total_duplicados = 0
    total_errores = 0

    logging.info("=" * 60)
    logging.info("INICIO DE SESIÓN DE EXTRACCIÓN")
    logging.info(f"Palabras clave: {len(palabras_clave)}")

    driver = inicializar_driver(headless=False)

    sesion_x = cargar_cookies_x(driver)
    sesion_fb = cargar_cookies_facebook(driver)

    if not sesion_x and not sesion_fb:
        logging.error(
            "No hay sesiones activas. "
            "Ejecuta guardar_sesiones.py primero."
        )
        driver.quit()
        return {
            'capturados': 0,
            'duplicados': 0,
            'errores': len(palabras_clave)
        }

    contador_reinicio = 0

    for palabra_clave in palabras_clave:
        logging.info(f"Procesando: '{palabra_clave}'")

        if contador_reinicio >= 7:
            logging.info("Reiniciando driver...")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(random.uniform(15, 25))
            driver = inicializar_driver(headless=False)
            if sesion_x:
                cargar_cookies_x(driver)
            if sesion_fb:
                cargar_cookies_facebook(driver)
            contador_reinicio = 0

        todas = []

        if sesion_x:
            todas.extend(extraer_de_x(driver, palabra_clave))
            time.sleep(random.uniform(5, 10))

        if sesion_fb:
            todas.extend(extraer_de_facebook(driver, palabra_clave))

        for pub in todas:
            try:
                if existe_publicacion(pub['id']):
                    total_duplicados += 1
                    continue
                insertar_reporte_crudo(
                    id_publicacion_plataforma=pub['id'],
                    plataforma=pub['plataforma'],
                    texto_crudo=pub['texto'],
                    url_publicacion=pub['url'],
                    fecha_publicacion=pub['fecha']
                )
                total_capturados += 1
            except Exception as e:
                logging.error(f"Error guardando: {str(e)}")
                total_errores += 1

        contador_reinicio += 1
        pausa = random.uniform(8, 20)
        logging.info(f"Pausa de {pausa:.1f}s.")
        time.sleep(pausa)

    # ---------------------------------------------------------------
    # Extracción adicional de grupos de Facebook
    # ---------------------------------------------------------------
    grupos_facebook = cargar_grupos_facebook()
    if grupos_facebook and sesion_fb:
        logging.info("=" * 40)
        logging.info("INICIO EXTRACCIÓN DE GRUPOS DE FACEBOOK")
        logging.info(f"Grupos a procesar: {len(grupos_facebook)}")

        try:
            driver.quit()
        except Exception:
            pass

        driver = inicializar_driver(headless=False)
        cargar_cookies_facebook(driver)
        time.sleep(random.uniform(3, 5))

        for url_grupo in grupos_facebook:
            logging.info(f"Procesando grupo: {url_grupo}")

            publicaciones_grupo = extraer_de_grupo_facebook(driver, url_grupo)
            logging.info(
                f"Publicaciones encontradas en grupo: "
                f"{len(publicaciones_grupo)}"
            )

            for pub in publicaciones_grupo:
                try:
                    if existe_publicacion(pub['id']):
                        total_duplicados += 1
                        continue
                    insertar_reporte_crudo(
                        id_publicacion_plataforma=pub['id'],
                        plataforma=pub['plataforma'],
                        texto_crudo=pub['texto'],
                        url_publicacion=pub['url'],
                        fecha_publicacion=pub['fecha']
                    )
                    total_capturados += 1
                except Exception as e:
                    logging.error(f"Error guardando post de grupo: {str(e)}")
                    total_errores += 1

            pausa = random.uniform(10, 20)
            logging.info(f"Pausa de {pausa:.1f}s entre grupos.")
            time.sleep(pausa)

        logging.info("FIN EXTRACCIÓN DE GRUPOS DE FACEBOOK")
        logging.info("=" * 40)

    try:
        driver.quit()
    except Exception:
        pass

    logging.info("FIN DE SESIÓN DE EXTRACCIÓN")
    logging.info(f"Capturados:  {total_capturados}")
    logging.info(f"Duplicados:  {total_duplicados}")
    logging.info(f"Errores:     {total_errores}")
    logging.info("=" * 60)

    return {
        'capturados': total_capturados,
        'duplicados': total_duplicados,
        'errores': total_errores
    }


def ejecutar_extraccion():
    """Punto de entrada del módulo de extracción."""
    palabras_clave = cargar_palabras_clave()
    resultado = extraer_publicaciones(palabras_clave)
    print(f"\nExtracción completada:")
    print(f"  Capturados:  {resultado['capturados']}")
    print(f"  Duplicados:  {resultado['duplicados']}")
    print(f"  Errores:     {resultado['errores']}")
    return resultado