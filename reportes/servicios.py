"""HU-20: indicadores de citas atendidas, canceladas y ausentes por rango de fechas."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from admision.models import Cita

MAX_DIAS = 366


@dataclass
class Resumen:
    inicio: date
    fin: date
    medico: object = None
    totales: dict = field(default_factory=dict)
    por_dia: list = field(default_factory=list)
    por_medico: list = field(default_factory=list)

    @property
    def total(self):
        return sum(self.totales.values())

    @property
    def tasa_asistencia(self):
        """Atendidas sobre las citas que ya debían ocurrir (atendidas + ausentes)."""
        base = self.totales['atendidas'] + self.totales['ausentes']
        return round(100 * self.totales['atendidas'] / base, 1) if base else None


def _conteos():
    hoy = timezone.localdate()
    pendiente = Q(estado__in=[Cita.AGENDADA, Cita.EN_ESPERA])
    return {
        'atendidas': Count('id', filter=Q(estado=Cita.ATENDIDA)),
        'canceladas': Count('id', filter=Q(estado=Cita.CANCELADA)),
        # Ausente: la cita ya pasó y el paciente nunca fue atendido ni la canceló
        'ausentes': Count('id', filter=pendiente & Q(fecha__lt=hoy)),
        'pendientes': Count('id', filter=pendiente & Q(fecha__gte=hoy)),
    }


def generar_resumen(inicio, fin, medico=None):
    if fin < inicio:
        inicio, fin = fin, inicio
    fin = min(fin, inicio + timedelta(days=MAX_DIAS - 1))
    citas = Cita.objects.filter(fecha__range=(inicio, fin))
    if medico:
        citas = citas.filter(medico=medico)

    resumen = Resumen(inicio, fin, medico)
    resumen.totales = citas.aggregate(**_conteos())

    dias = {fila['fecha']: fila for fila in citas.values('fecha').annotate(**_conteos())}
    vacio = dict.fromkeys(('atendidas', 'canceladas', 'ausentes', 'pendientes'), 0)
    actual = inicio
    while actual <= fin:
        resumen.por_dia.append({'fecha': actual, **vacio, **{k: v for k, v in dias.get(actual, {}).items() if k != 'fecha'}})
        actual += timedelta(days=1)

    resumen.por_medico = list(
        citas.values('medico__first_name', 'medico__last_name', 'medico__username')
        .annotate(**_conteos()).order_by('medico__last_name', 'medico__first_name'))
    return resumen
