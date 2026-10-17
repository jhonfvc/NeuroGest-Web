from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Usuario

# HU-04: roles permitidos por módulo (prefijo de URL). El Administrador entra a todo.
PERMISOS_POR_MODULO = {
    '/usuarios/': (Usuario.ADMIN,),
    '/admision/': (Usuario.ADMIN, Usuario.RECEPCION),
    '/hce/': (Usuario.ADMIN, Usuario.MEDICO),
    '/reportes/': (Usuario.ADMIN,),
}


def tiene_rol(user, roles):
    return user.is_authenticated and (user.es_admin or user.rol in roles)


def acceso_denegado(request):
    return render(request, 'seguridad/403.html', status=403)


def rol_requerido(*roles):
    """Restringe una vista a los roles indicados (el Administrador siempre pasa)."""
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if not tiene_rol(request.user, roles):
                return acceso_denegado(request)
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador
