from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


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
    if request.user.rol == 'MEDICO':
        return render(request, 'seguridad/dashboard_medico.html')
    elif request.user.rol == 'RECEPCION':
        return render(request, 'seguridad/dashboard_recepcion.html')
    else:
        return render(request, 'seguridad/dashboard_admin.html')


def user_logout(request):
    logout(request)
    return redirect('login')