from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Usuario

# HU-04: el administrador solo asigna los roles operativos
ROLES_ASIGNABLES = [r for r in Usuario.ROLES if r[0] != Usuario.ADMIN]

CLASE_INPUT = 'mt-1 w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none'


class EstiloTailwindMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', CLASE_INPUT)


class UsuarioCreacionForm(EstiloTailwindMixin, UserCreationForm):
    """HU-03: alta de usuarios de Recepción y Médico."""
    rol = forms.ChoiceField(choices=ROLES_ASIGNABLES, label='Rol en el Sistema')

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'dni', 'telefono', 'rol')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ('first_name', 'last_name', 'dni'):
            self.fields[nombre].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email


class RolForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-04: cambio de rol de un usuario existente."""
    rol = forms.ChoiceField(choices=ROLES_ASIGNABLES, label='Rol en el Sistema')

    class Meta:
        model = Usuario
        fields = ('rol',)
