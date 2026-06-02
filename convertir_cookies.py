import json
import pickle
import os

COOKIES_X_JSON = os.path.join('config', 'cookies_x_manual.json')
COOKIES_FB_JSON = os.path.join('config', 'cookies_fb_manual.json')
COOKIES_X_PKL = os.path.join('config', 'cookies_x.pkl')
COOKIES_FB_PKL = os.path.join('config', 'cookies_facebook.pkl')


def convertir_cookies(json_path, pkl_path, nombre):
    if not os.path.exists(json_path):
        print(f"No se encontró {json_path}. Saltando...")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    # Adaptar formato de Cookie-Editor al formato que espera Selenium
    cookies_selenium = []
    for cookie in cookies:
        cookie_selenium = {
            'name': cookie.get('name', ''),
            'value': cookie.get('value', ''),
            'domain': cookie.get('domain', ''),
            'path': cookie.get('path', '/'),
            'secure': cookie.get('secure', False),
        }
        # Solo agregar si tiene sameSite válido
        if 'sameSite' in cookie and cookie['sameSite'] in ['Strict', 'Lax', 'None']:
            cookie_selenium['sameSite'] = cookie['sameSite']

        # Agregar expiración si existe
        if 'expirationDate' in cookie:
            cookie_selenium['expiry'] = int(cookie['expirationDate'])

        cookies_selenium.append(cookie_selenium)

    with open(pkl_path, 'wb') as f:
        pickle.dump(cookies_selenium, f)

    print(f"{nombre}: {len(cookies_selenium)} cookies convertidas y guardadas.")


if __name__ == "__main__":
    print("Convirtiendo cookies...\n")
    convertir_cookies(COOKIES_X_JSON, COOKIES_X_PKL, "X")
    convertir_cookies(COOKIES_FB_JSON, COOKIES_FB_PKL, "Facebook")
    print("\nListo. Ya puedes ejecutar test_extraccion.py")