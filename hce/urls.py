from django.urls import path

from reportes.views import descargar_receta

from . import views

# Montado en /hce/ (solo Médico y Administrador, ver seguridad.permisos)
urlpatterns = [
    path('', views.buscar, name='buscar_expediente'),
    path('api/buscar/', views.api_buscar, name='api_buscar_expediente'),
    path('api/cie10/', views.api_cie10, name='api_cie10'),
    path('paciente/<int:pk>/', views.expediente, name='expediente'),
    path('paciente/<int:pk>/historial/', views.historial, name='historial'),
    path('paciente/<int:paciente_pk>/atencion/', views.nueva_atencion, name='nueva_atencion_paciente'),
    path('cita/<int:cita_pk>/atencion/', views.nueva_atencion, name='nueva_atencion'),
    path('atencion/<int:pk>/', views.detalle_atencion, name='detalle_atencion'),
    path('atencion/<int:pk>/receta.pdf', descargar_receta, name='receta_pdf'),
]
