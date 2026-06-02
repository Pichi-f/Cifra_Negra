from modulos.extraccion import guardar_cookies_x, guardar_cookies_facebook

print("Este script guarda tus sesiones para la extracción.")
print("Solo necesitas ejecutarlo una vez.\n")

guardar_cookies_x()
guardar_cookies_facebook()

print("\nSesiones guardadas. Ya puedes ejecutar test_extraccion.py")