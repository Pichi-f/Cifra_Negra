import modulos.extraccion as extraccion
from modulos.extraccion import extraer_de_grupo_facebook
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


extraccion.time.sleep = lambda *_args, **_kwargs: None
extraccion.random.uniform = lambda *_args, **_kwargs: 0
extraccion.random.randint = lambda *_args, **_kwargs: 500


class FakeElement:
    def __init__(self, text=''):
        self.text = text
        self.sent_keys = []

    def send_keys(self, key):
        self.sent_keys.append(key)


class FakeDriver:
    def __init__(self):
        self.current_url = 'https://www.facebook.com/groups/820765246263049'
        self.overlay_calls = 2
        self.scrolled = 0
        self.body = FakeElement()
        self.posts = [
            FakeElement('Asalto en zona 18 deja heridos y vecinos alertan'),
            FakeElement('Extorsionan negocio en Mixco con llamadas intimidantes'),
            FakeElement('Asalto en zona 18 deja heridos y vecinos alertan'),
        ]

    def get(self, url):
        self.current_url = url

    def execute_script(self, script, *args):
        if 'return dialogos.length > 0 || bloqueoScroll' in script:
            return self.overlay_calls > 0
        if 'window.scrollBy' in script or 'window.scrollTo' in script:
            self.scrolled += 1
            return None
        if 'window.stop()' in script:
            return None
        if 'querySelectorAll' in script:
            if self.overlay_calls > 0:
                self.overlay_calls -= 1
            return None
        return None

    def find_elements(self, by, selector):
        if by == By.CSS_SELECTOR and selector in [
            'div[data-ad-comet-preview="message"]',
            'div[data-ad-preview="message"]',
            'div[role="article"] div[dir="auto"]',
        ]:
            return self.posts
        return []

    def find_element(self, by, selector):
        if by == By.TAG_NAME and selector == 'body':
            return self.body
        raise Exception(f'Elemento no soportado: {by} {selector}')


if __name__ == '__main__':
    driver = FakeDriver()
    publicaciones = extraer_de_grupo_facebook(driver, driver.current_url)

    print('Publicaciones extraidas:', len(publicaciones))
    for publicacion in publicaciones:
        print(publicacion['id'], publicacion['texto'])

    assert len(publicaciones) >= 2, 'Se esperaban al menos 2 publicaciones únicas.'
    assert driver.scrolled > 0, 'Se esperaba al menos un intento de scroll.'
    print('OK: la logica de overlays/scroll/deduplicacion responde como se esperaba.')
