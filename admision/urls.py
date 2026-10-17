from django.urls import path
from . import views

# Montado en /admision/ (solo Recepción y Administrador, ver seguridad.permisos)
urlpatterns = [
    path('pacientes/', views.lista_pacientes, name='lista_pacientes'),
    path('pacientes/nuevo/', views.registrar_paciente, name='registrar_paciente'),
    path('api/dni/<str:dni>/', views.api_consulta_dni, name='api_consulta_dni'),
]
