from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from seguridad.models import validar_dni

# Horario de atención del consultorio (HU-NF05: 8:00 a 20:00 h)
HORA_APERTURA = time(8, 0)
HORA_CIERRE = time(20, 0)
DURACION_CITA = timedelta(minutes=30)


class Paciente(models.Model):
    API = 'API'
    MANUAL = 'MANUAL'
    ORIGENES = ((API, 'API RENIEC'), (MANUAL, 'Registro manual'))

    SEXOS = (('M', 'Masculino'), ('F', 'Femenino'))

    numero_historia = models.CharField(max_length=10, unique=True, editable=False, verbose_name='N° de Historia')
    dni = models.CharField(max_length=8, unique=True, validators=[validar_dni], verbose_name='DNI')
    nombres = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=60, verbose_name='Apellido paterno')
    apellido_materno = models.CharField(max_length=60, blank=True, verbose_name='Apellido materno')
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name='Fecha de nacimiento')
    sexo = models.CharField(max_length=1, choices=SEXOS, blank=True)
    telefono = models.CharField(max_length=15, blank=True, verbose_name='Teléfono')
    direccion = models.CharField(max_length=200, blank=True, verbose_name='Dirección')
    # HU-07: registro auditable del origen de los datos
    origen = models.CharField(max_length=6, choices=ORIGENES, default=MANUAL, editable=False)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                       related_name='pacientes_registrados', editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['apellido_paterno', 'apellido_materno', 'nombres']
        indexes = [models.Index(fields=['apellido_paterno', 'apellido_materno'])]

    def __str__(self):
        return f"{self.nombre_completo} (DNI {self.dni})"

    @property
    def nombre_completo(self):
        return ' '.join(p for p in (self.nombres, self.apellido_paterno, self.apellido_materno) if p)

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        hoy = timezone.localdate()
        nac = self.fecha_nacimiento
        return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))

    def save(self, *args, **kwargs):
        if not self.numero_historia:
            ultimo = Paciente.objects.order_by('-id').values_list('id', flat=True).first() or 0
            self.numero_historia = f"HC-{ultimo + 1:06d}"
        super().save(*args, **kwargs)


class CitaQuerySet(models.QuerySet):
    def activas(self):
        return self.exclude(estado=Cita.CANCELADA)

    def del_dia(self, fecha):
        return self.filter(fecha=fecha)


class Cita(models.Model):
    AGENDADA = 'AGENDADA'
    EN_ESPERA = 'EN_ESPERA'
    ATENDIDA = 'ATENDIDA'
    CANCELADA = 'CANCELADA'
    ESTADOS = (
        (AGENDADA, 'Agendada'),
        (EN_ESPERA, 'En espera'),
        (ATENDIDA, 'Atendida'),
        (CANCELADA, 'Cancelada'),
    )

    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='citas')
    medico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='citas_medico',
                               limit_choices_to={'rol': 'MEDICO', 'is_active': True}, verbose_name='Médico')
    fecha = models.DateField()
    hora = models.TimeField()
    motivo = models.CharField(max_length=200, blank=True, verbose_name='Motivo de consulta')
    estado = models.CharField(max_length=10, choices=ESTADOS, default=AGENDADA)
    motivo_cancelacion = models.CharField(max_length=200, blank=True, verbose_name='Motivo de cancelación')
    llegada_en = models.DateTimeField(null=True, blank=True, verbose_name='Hora de llegada')
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name='citas_registradas', editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = CitaQuerySet.as_manager()

    class Meta:
        ordering = ['fecha', 'hora']
        indexes = [models.Index(fields=['fecha', 'medico'])]
        constraints = [
            # Respaldo en BD ante dos registros simultáneos del mismo turno
            models.UniqueConstraint(fields=['medico', 'fecha', 'hora'], condition=~models.Q(estado='CANCELADA'),
                                    name='cita_unica_por_turno_activo'),
        ]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} {self.hora:%H:%M} - {self.paciente.nombre_completo}"

    @property
    def inicio(self):
        return datetime.combine(self.fecha, self.hora)

    @property
    def editable(self):
        return self.estado in (self.AGENDADA, self.EN_ESPERA)

    def clean(self):
        errores = {}
        if self.hora:
            if not (HORA_APERTURA <= self.hora and (datetime.combine(datetime.min, self.hora) + DURACION_CITA).time() <= HORA_CIERRE):
                errores['hora'] = 'La hora debe estar dentro del horario de atención (8:00 a 20:00).'
            elif self.hora.minute % 30 or self.hora.second:
                errores['hora'] = 'Las citas se programan en turnos de 30 minutos.'
        if self.medico_id and self.medico.rol != 'MEDICO':
            errores['medico'] = 'El usuario seleccionado no es un médico.'
        if self.fecha and self.hora and self._state.adding and self.inicio < timezone.localtime().replace(tzinfo=None):
            errores['fecha'] = 'No se puede agendar una cita en el pasado.'
        if errores:
            raise ValidationError(errores)
        if self.medico_id and self.fecha and self.hora and self.estado != self.CANCELADA and self.hay_cruce():
            raise ValidationError({'hora': 'El médico ya tiene una cita en ese horario.'})

    def hay_cruce(self):
        """HU-08 / HU-10: el médico no puede tener dos citas activas en el mismo turno."""
        return (Cita.objects.activas()
                .filter(medico_id=self.medico_id, fecha=self.fecha, hora=self.hora)
                .exclude(pk=self.pk).exists())


def turnos_del_dia():
    actual = datetime.combine(datetime.min, HORA_APERTURA)
    fin = datetime.combine(datetime.min, HORA_CIERRE)
    while actual + DURACION_CITA <= fin:
        yield actual.time()
        actual += DURACION_CITA


def turnos_disponibles(medico, fecha, excluir_cita=None):
    ocupados = set(Cita.objects.activas().filter(medico=medico, fecha=fecha)
                   .exclude(pk=getattr(excluir_cita, 'pk', None)).values_list('hora', flat=True))
    ahora = timezone.localtime().replace(tzinfo=None)
    return [t for t in turnos_del_dia() if t not in ocupados and datetime.combine(fecha, t) > ahora]
