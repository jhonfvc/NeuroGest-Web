from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'email', 'dni', 'rol', 'is_active')
    list_filter = ('rol', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'dni')
    fieldsets = UserAdmin.fieldsets + (
        ('Datos de NeuroGest', {'fields': ('rol', 'dni', 'telefono')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos de NeuroGest', {'fields': ('email', 'rol', 'dni', 'telefono')}),
    )
