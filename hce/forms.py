from django import forms

from seguridad.forms import EstiloTailwindMixin

from .models import Atencion, Cie10, Prescripcion, Triaje


class TextareaCorta(forms.Textarea):
    def __init__(self, filas=3):
        super().__init__(attrs={'rows': filas})


class TriajeForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-15: PA, peso y talla obligatorios; el IMC se calcula al guardar."""

    class Meta:
        model = Triaje
        fields = ('presion_sistolica', 'presion_diastolica', 'peso', 'talla',
                  'frecuencia_cardiaca', 'temperatura', 'saturacion')
        widgets = {
            'peso': forms.NumberInput(attrs={'step': '0.1'}),
            'talla': forms.NumberInput(attrs={'step': '0.1'}),
            'temperatura': forms.NumberInput(attrs={'step': '0.1'}),
        }


class AtencionForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-16 / HU-17: evolución médica con diagnóstico CIE-10 obligatorio."""
    diagnosticos = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Atencion
        fields = ('motivo_consulta', 'anamnesis', 'examen_fisico', 'examen_neurologico', 'evolucion', 'plan')
        widgets = {
            'motivo_consulta': TextareaCorta(2),
            'anamnesis': TextareaCorta(4),
            'examen_fisico': TextareaCorta(3),
            'examen_neurologico': TextareaCorta(4),
            'evolucion': TextareaCorta(4),
            'plan': TextareaCorta(3),
        }

    def clean_diagnosticos(self):
        """Lista de ids CIE-10 separados por coma; el primero es el diagnóstico principal."""
        ids = []
        for valor in self.cleaned_data.get('diagnosticos', '').split(','):
            if valor.strip().isdigit() and int(valor) not in ids:
                ids.append(int(valor))
        if not ids:
            raise forms.ValidationError('Registra al menos un diagnóstico CIE-10.')
        encontrados = Cie10.objects.in_bulk(ids)
        if len(encontrados) != len(ids):
            raise forms.ValidationError('Uno de los diagnósticos seleccionados no existe en el catálogo.')
        return [encontrados[i] for i in ids]


class PrescripcionForm(EstiloTailwindMixin, forms.ModelForm):
    """HU-18 / HU-NF09: medicamento con validación de rangos de dosis."""

    class Meta:
        model = Prescripcion
        fields = ('medicamento', 'presentacion', 'dosis', 'unidad', 'via', 'frecuencia_horas', 'duracion_dias', 'indicaciones')
        widgets = {'dosis': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'})}


PrescripcionFormSet = forms.inlineformset_factory(
    Atencion, Prescripcion, form=PrescripcionForm, extra=0, can_delete=False, max_num=15, validate_max=True,
)
