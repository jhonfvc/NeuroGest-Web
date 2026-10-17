from django.urls import path
from . import views

# Montado en /citas/ (permisos por vista: la agenda la ven Recepción y Médico)
urlpatterns = [
    path('agenda/', views.agenda, name='agenda'),
    path('calendario/', views.calendario, name='calendario'),
    path('nueva/', views.nueva_cita, name='nueva_cita'),
    path('disponibilidad/', views.api_disponibilidad, name='api_disponibilidad'),
    path('en-espera/', views.api_en_espera, name='api_en_espera'),
    path('<int:pk>/reprogramar/', views.reprogramar_cita, name='reprogramar_cita'),
    path('<int:pk>/cancelar/', views.cancelar_cita, name='cancelar_cita'),
    path('<int:pk>/llegada/', views.confirmar_llegada, name='confirmar_llegada'),
]
