from django.contrib.auth.views import redirect_to_login

from .permisos import PERMISOS_POR_MODULO, acceso_denegado, tiene_rol


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
