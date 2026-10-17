from django.contrib import admin

from .models import Atencion, Cie10, Diagnostico, Prescripcion, Triaje


@admin.register(Cie10)
class Cie10Admin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion')
    search_fields = ('codigo', 'descripcion')


class TriajeInline(admin.StackedInline):
    model = Triaje
    readonly_fields = ('imc',)
    can_delete = False


class DiagnosticoInline(admin.TabularInline):
    model = Diagnostico
    autocomplete_fields = ('cie10',)
    extra = 0


class PrescripcionInline(admin.TabularInline):
    model = Prescripcion
    extra = 0


@admin.register(Atencion)
class AtencionAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'paciente', 'medico')
    search_fields = ('paciente__dni', 'paciente__apellido_paterno')
    inlines = (TriajeInline, DiagnosticoInline, PrescripcionInline)

    # El expediente clínico es de solo lectura desde el admin
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
