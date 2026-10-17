from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import RolForm, UsuarioCreacionForm
from .models import Usuario
from .permisos import acceso_denegado, rol_requerido


def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username_req = request.POST.get('username')
        password_req = request.POST.get('password')

        user = authenticate(
            request, username=username_req, password=password_req
        )

        if user is not None:
            login(request, user)
            messages.success(
                request, f"Bienvenido(a) {user.first_name or user.username}"
            )
            return redirect('dashboard')
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")

    return render(request, 'seguridad/login.html')


@login_required
def dashboard(request):
    # Redirección según el rol asignado
    if request.user.es_admin:
        return render(request, 'seguridad/dashboard_admin.html')
    elif request.user.rol == Usuario.MEDICO:
        return render(request, 'seguridad/dashboard_medico.html')
    elif request.user.rol == Usuario.RECEPCION:
        return render(request, 'seguridad/dashboard_recepcion.html')
    return acceso_denegado(request)


@require_POST
def user_logout(request):
    logout(request)
    return redirect('login')


@rol_requerido(Usuario.ADMIN)
def lista_usuarios(request):
    usuarios = Usuario.objects.order_by('-is_active', 'last_name', 'username')
    return render(request, 'seguridad/usuarios/lista.html', {'usuarios': usuarios})


@rol_requerido(Usuario.ADMIN)
def crear_usuario(request):
    # HU-03: registro de cuentas de Recepción y Médico
    form = UsuarioCreacionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = form.save()
        messages.success(request, f"Usuario {usuario.username} creado correctamente.")
        return redirect('lista_usuarios')
    return render(request, 'seguridad/usuarios/form.html', {'form': form, 'titulo': 'Nuevo usuario'})


@rol_requerido(Usuario.ADMIN)
def cambiar_rol(request, pk):
    # HU-04: asignación de rol Recepción o Médico
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.es_admin:
        messages.error(request, "No se puede cambiar el rol de un administrador.")
        return redirect('lista_usuarios')
    form = RolForm(request.POST or None, instance=usuario)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"Rol de {usuario.username} actualizado a {usuario.get_rol_display()}.")
        return redirect('lista_usuarios')
    return render(request, 'seguridad/usuarios/form.html', {
        'form': form, 'titulo': f'Cambiar rol de {usuario.username}',
    })


@require_POST
@rol_requerido(Usuario.ADMIN)
def cambiar_estado(request, pk):
    # HU-05: activar/desactivar por borrado lógico, sin eliminar registros
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario == request.user:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
    else:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=['is_active'])
        estado = 'activada' if usuario.is_active else 'desactivada'
        messages.success(request, f"Cuenta de {usuario.username} {estado}.")
    return redirect('lista_usuarios')
