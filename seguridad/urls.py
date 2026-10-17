from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path('', views.user_login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.user_logout, name='logout'),

    # HU-03, HU-04, HU-05: administración de usuarios
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/nuevo/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/<int:pk>/rol/', views.cambiar_rol, name='cambiar_rol'),
    path('usuarios/<int:pk>/estado/', views.cambiar_estado, name='cambiar_estado'),

    # HU-02: recuperación de contraseña por correo
    path('recuperar/', auth_views.PasswordResetView.as_view(
        template_name='seguridad/recuperar/solicitar.html',
        email_template_name='seguridad/recuperar/email.txt',
        subject_template_name='seguridad/recuperar/asunto.txt',
    ), name='password_reset'),
    path('recuperar/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='seguridad/recuperar/enviado.html',
    ), name='password_reset_done'),
    path('recuperar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='seguridad/recuperar/nueva_clave.html',
    ), name='password_reset_confirm'),
    path('recuperar/listo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='seguridad/recuperar/listo.html',
    ), name='password_reset_complete'),
]
