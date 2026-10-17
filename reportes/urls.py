from django.urls import path
from . import views

# Montado en /reportes/ (solo Administrador, ver seguridad.permisos)
urlpatterns = [
    path('', views.panel, name='reportes'),
    path('excel/', views.exportar_excel, name='reporte_excel'),
    path('pdf/', views.exportar_pdf, name='reporte_pdf'),
]
