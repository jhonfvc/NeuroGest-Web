from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from admision.models import Cita, Paciente


class Cie10(models.Model):
    """HU-17: catálogo de diagnósticos CIE-10."""
    codigo = models.CharField(max_length=7, unique=True, verbose_name='Código')
    descripcion = models.CharField(max_length=255, verbose_name='Descripción')

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Diagnóstico CIE-10'
        verbose_name_plural = 'Catálogo CIE-10'

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"


class Atencion(models.Model):
    """HU-16: atención médica (evolución). Una vez registrada no se modifica."""
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='atenciones')
    medico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='atenciones')
    cita = models.OneToOneField(Cita, null=True, blank=True, on_delete=models.PROTECT, related_name='atencion')
    # Timestamp inmutable de la atención
    fecha = models.DateTimeField(auto_now_add=True, editable=False)
    motivo_consulta = models.TextField(verbose_name='Motivo de consulta')
    anamnesis = models.TextField(blank=True, verbose_name='Anamnesis')
    examen_fisico = models.TextField(blank=True, verbose_name='Examen físico')
    examen_neurologico = models.TextField(blank=True, verbose_name='Examen neurológico')
    evolucion = models.TextField(verbose_name='Evolución / notas')
    plan = models.TextField(blank=True, verbose_name='Plan de trabajo e indicaciones')

    class Meta:
        ordering = ['-fecha']
        verbose_name_plural = 'Atenciones'

    def __str__(self):
        return f"Atención {self.fecha:%d/%m/%Y %H:%M} - {self.paciente.nombre_completo}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Las atenciones registradas no se pueden modificar.')
        super().save(*args, **kwargs)

    @property
    def diagnostico_principal(self):
        return self.diagnosticos.filter(principal=True).select_related('cie10').first()


class Triaje(models.Model):
    """HU-15: funciones vitales con IMC calculado automáticamente."""
    atencion = models.OneToOneField(Atencion, on_delete=models.CASCADE, related_name='triaje')
    presion_sistolica = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(50), MaxValueValidator(260)], verbose_name='PA sistólica (mmHg)')
    presion_diastolica = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(30), MaxValueValidator(160)], verbose_name='PA diastólica (mmHg)')
    peso = models.DecimalField(max_digits=5, decimal_places=2,
                               validators=[MinValueValidator(Decimal('1')), MaxValueValidator(Decimal('350'))],
                               verbose_name='Peso (kg)')
    talla = models.DecimalField(max_digits=5, decimal_places=2,
                                validators=[MinValueValidator(Decimal('40')), MaxValueValidator(Decimal('250'))],
                                verbose_name='Talla (cm)')
    imc = models.DecimalField(max_digits=5, decimal_places=2, editable=False, verbose_name='IMC')
    frecuencia_cardiaca = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(20), MaxValueValidator(250)], verbose_name='FC (lpm)')
    temperatura = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal('30')), MaxValueValidator(Decimal('45'))], verbose_name='Temperatura (°C)')
    saturacion = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(50), MaxValueValidator(100)], verbose_name='SatO₂ (%)')

    @staticmethod
    def calcular_imc(peso, talla_cm):
        metros = Decimal(talla_cm) / 100
        return (Decimal(peso) / (metros * metros)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def clasificacion_imc(self):
        if self.imc < Decimal('18.5'):
            return 'Bajo peso'
        if self.imc < 25:
            return 'Normal'
        if self.imc < 30:
            return 'Sobrepeso'
        return 'Obesidad'

    def clean(self):
        if self.presion_sistolica and self.presion_diastolica and self.presion_diastolica >= self.presion_sistolica:
            raise ValidationError({'presion_diastolica': 'La diastólica debe ser menor que la sistólica.'})

    def save(self, *args, **kwargs):
        self.imc = self.calcular_imc(self.peso, self.talla)
        super().save(*args, **kwargs)


class Diagnostico(models.Model):
    """HU-17: vinculación diagnóstico CIE-10 - atención."""
    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name='diagnosticos')
    cie10 = models.ForeignKey(Cie10, on_delete=models.PROTECT, related_name='diagnosticos')
    principal = models.BooleanField(default=False)

    class Meta:
        ordering = ['-principal', 'id']
        constraints = [models.UniqueConstraint(fields=['atencion', 'cie10'], name='diagnostico_unico_por_atencion')]

    def __str__(self):
        return str(self.cie10)


class Prescripcion(models.Model):
    """HU-18: medicamento de la receta asociada a la atención."""
    UNIDADES = (
        ('mg', 'mg'), ('g', 'g'), ('mcg', 'mcg'), ('ml', 'ml'),
        ('tab', 'tableta(s)'), ('cap', 'cápsula(s)'), ('gotas', 'gotas'), ('amp', 'ampolla(s)'),
    )
    # HU-NF09: dosis máxima por toma según la unidad, para prevenir errores de digitación
    DOSIS_MAXIMA = {'mg': 3000, 'g': 4, 'mcg': 5000, 'ml': 60, 'tab': 4, 'cap': 4, 'gotas': 60, 'amp': 2}
    VIAS = (('VO', 'Oral'), ('SL', 'Sublingual'), ('IM', 'Intramuscular'), ('EV', 'Endovenosa'),
            ('SC', 'Subcutánea'), ('TOP', 'Tópica'), ('INH', 'Inhalatoria'))

    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name='prescripciones')
    medicamento = models.CharField(max_length=120, verbose_name='Medicamento (DCI)')
    presentacion = models.CharField(max_length=80, blank=True, verbose_name='Presentación / concentración')
    dosis = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unidad = models.CharField(max_length=5, choices=UNIDADES, default='mg')
    via = models.CharField(max_length=3, choices=VIAS, default='VO', verbose_name='Vía')
    frecuencia_horas = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(72)], verbose_name='Cada (horas)')
    duracion_dias = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(365)], verbose_name='Duración (días)')
    indicaciones = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name_plural = 'Prescripciones'

    def __str__(self):
        return f"{self.medicamento} {self.dosis} {self.unidad} c/{self.frecuencia_horas} h x {self.duracion_dias} d"

    @property
    def posologia(self):
        return (f"{self.dosis.normalize():f} {self.get_unidad_display()} vía {self.get_via_display().lower()} "
                f"cada {self.frecuencia_horas} h por {self.duracion_dias} día(s)")

    def clean(self):
        maximo = self.DOSIS_MAXIMA.get(self.unidad)
        if self.dosis and maximo and self.dosis > maximo:
            raise ValidationError({'dosis': f'La dosis supera el máximo permitido por toma ({maximo} {self.unidad}).'})
