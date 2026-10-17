from django.contrib import admin

from .models import Cita, Paciente


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('numero_historia', 'dni', 'nombres', 'apellido_paterno', 'apellido_materno', 'origen', 'creado_en')
    list_filter = ('origen',)
    search_fields = ('dni', 'nombres', 'apellido_paterno', 'apellido_materno', 'numero_historia')
    readonly_fields = ('numero_historia', 'origen', 'registrado_por', 'creado_en')


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'hora', 'paciente', 'medico', 'estado')
    list_filter = ('estado', 'medico', 'fecha')
    search_fields = ('paciente__dni', 'paciente__apellido_paterno')
    readonly_fields = ('creado_por', 'creado_en', 'actualizado_en', 'llegada_en')
