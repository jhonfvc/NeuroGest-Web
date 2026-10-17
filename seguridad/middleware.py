import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse

from .permisos import PERMISOS_POR_MODULO, acceso_denegado, tiene_rol

# Consultas automáticas (polling) que no cuentan como actividad del usuario
RUTAS_PASIVAS = ('/citas/en-espera/',)


class InactividadMiddleware:
    """HU-NF06: cierra la sesión tras 15 minutos sin interacción real del usuario."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            ahora = time.time()
            pasiva = request.path.startswith(RUTAS_PASIVAS)
            ultima = request.session.get('ultima_actividad', ahora)
            if ahora - ultima > settings.SESSION_COOKIE_AGE:
                logout(request)
                if pasiva:
                    return JsonResponse({'error': 'sesion_expirada'}, status=401)
                return redirect_to_login(request.get_full_path())
            if not pasiva:
                request.session['ultima_actividad'] = ahora
        return self.get_response(request)


class RolMiddleware:
    """HU-04: bloquea el acceso a cada módulo según el rol del usuario."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for prefijo, roles in PERMISOS_POR_MODULO.items():
            if request.path.startswith(prefijo):
                if not request.user.is_authenticated:
                    return redirect_to_login(request.get_full_path())
                if not tiene_rol(request.user, roles):
                    return acceso_denegado(request)
                break
        return self.get_response(request)
