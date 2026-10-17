from django import forms
from django.utils import timezone

from seguridad.forms import EstiloTailwindMixin
from seguridad.models import Usuario

from .models import Cita, Paciente, turnos_del_dia

TURNOS = [(t.strftime('%H:%M'), t.strftime('%H:%M')) for t in turnos_del_dia()]


def medicos_activos():
    return Usuario.objects.filter(rol=Usuario.MEDICO, is_active=True).order_by('last_name', 'first_name')


class MedicoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"Dr(a). {obj.get_full_name() or obj.username}"


class PacienteForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-06 / HU-07: registro de paciente (autocompletado por API o manual)."""

    class Meta:
        model = Paciente
        fields = ('dni', 'nombres', 'apellido_paterno', 'apellido_materno', 'fecha_nacimiento',
                  'sexo', 'telefono', 'direccion')
        widgets = {'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dni'].widget.attrs.update({'inputmode': 'numeric', 'maxlength': 8, 'pattern': r'\d{8}'})

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get('fecha_nacimiento')
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de nacimiento no puede ser futura.')
        return fecha


class CitaForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-08: agendamiento de cita."""
    paciente_dni = forms.CharField(label='DNI del paciente', max_length=8)
    medico = MedicoChoiceField(queryset=Usuario.objects.none(), label='Médico')
    hora = forms.TimeField(widget=forms.Select(choices=TURNOS), input_formats=['%H:%M'])

    class Meta:
        model = Cita
        fields = ('medico', 'fecha', 'hora', 'motivo')
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    field_order = ('paciente_dni', 'medico', 'fecha', 'hora', 'motivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['medico'].queryset = medicos_activos()
        self.fields['fecha'].widget.attrs['min'] = timezone.localdate().isoformat()
        self.fields['paciente_dni'].widget.attrs.update({'inputmode': 'numeric', 'maxlength': 8})

    def clean_paciente_dni(self):
        dni = self.cleaned_data['paciente_dni'].strip()
        try:
            self.instance.paciente = Paciente.objects.get(dni=dni)
        except Paciente.DoesNotExist:
            raise forms.ValidationError('No hay un paciente registrado con ese DNI. Regístralo primero.')
        return dni


class ReprogramarForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-10: cambio de fecha/hora con revalidación de disponibilidad."""
    hora = forms.TimeField(widget=forms.Select(choices=TURNOS), input_formats=['%H:%M'])

    class Meta:
        model = Cita
        fields = ('fecha', 'hora')
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def clean(self):
        datos = super().clean()
        fecha, hora = datos.get('fecha'), datos.get('hora')
        if fecha and hora:
            from datetime import datetime
            if datetime.combine(fecha, hora) <= timezone.localtime().replace(tzinfo=None):
                raise forms.ValidationError('La nueva fecha y hora deben ser futuras.')
        return datos


class CancelarForm(forms.Form):
    """HU-11: el motivo de cancelación es obligatorio."""
    motivo_cancelacion = forms.CharField(label='Motivo de cancelación', max_length=200, min_length=3)
