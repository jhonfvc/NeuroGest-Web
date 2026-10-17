from datetime import date, datetime, timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from django.core.exceptions import ValidationError

from seguridad.models import Usuario, validar_dni
from seguridad.permisos import rol_requerido

from .forms import CancelarForm, CitaForm, PacienteForm, ReprogramarForm, medicos_activos
from .models import Cita, Paciente, turnos_del_dia, turnos_disponibles
from .reniec import DniNoEncontrado, ReniecNoDisponible, consultar_dni

RECEPCION = (Usuario.RECEPCION,)
AGENDA = (Usuario.RECEPCION, Usuario.MEDICO)
CLAVE_SESION_DNI = 'dni_api'


def _fecha_param(valor, defecto=None):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return defecto or timezone.localdate()


# ---------- Pacientes (HU-06, HU-07) ----------

@rol_requerido(*RECEPCION)
def lista_pacientes(request):
    q = request.GET.get('q', '').strip()
    pacientes = Paciente.objects.all()
    if q:
        pacientes = pacientes.filter(
            Q(dni__startswith=q) | Q(nombres__icontains=q) | Q(apellido_paterno__icontains=q)
            | Q(apellido_materno__icontains=q) | Q(numero_historia__iexact=q))
    return render(request, 'admision/pacientes/lista.html', {'pacientes': pacientes[:100], 'q': q})


@require_GET
@rol_requerido(*RECEPCION)
def api_consulta_dni(request, dni):
    """HU-06: autocompletado desde RENIEC. Responde modo='manual' si la API falla (HU-07)."""
    try:
        validar_dni(dni)
    except ValidationError:
        return JsonResponse({'ok': False, 'error': 'El DNI debe tener 8 dígitos.'}, status=400)

    existente = Paciente.objects.filter(dni=dni).first()
    if existente:
        return JsonResponse({'ok': False, 'existe': True, 'paciente': existente.nombre_completo,
                             'numero_historia': existente.numero_historia,
                             'url_cita': f"{reverse('nueva_cita')}?dni={dni}"}, status=409)
    try:
        datos = consultar_dni(dni)
    except DniNoEncontrado:
        return JsonResponse({'ok': False, 'modo': 'manual', 'error': 'El DNI no figura en RENIEC. Registra los datos manualmente.'}, status=404)
    except ReniecNoDisponible:
        return JsonResponse({'ok': False, 'modo': 'manual', 'error': 'El servicio de DNI no responde. Se activó el registro manual.'}, status=503)

    request.session[CLAVE_SESION_DNI] = datos.como_dict()
    return JsonResponse({'ok': True, 'datos': datos.como_dict()})


def _origen(request, paciente):
    """El origen API solo se acepta si los datos coinciden con la última consulta real a RENIEC."""
    consultado = request.session.pop(CLAVE_SESION_DNI, None) or {}
    coincide = (consultado.get('dni') == paciente.dni
                and consultado.get('nombres') == paciente.nombres
                and consultado.get('apellido_paterno') == paciente.apellido_paterno
                and consultado.get('apellido_materno') == paciente.apellido_materno)
    return Paciente.API if coincide else Paciente.MANUAL


@rol_requerido(*RECEPCION)
def registrar_paciente(request):
    form = PacienteForm(request.POST or None, initial={'dni': request.GET.get('dni', '')})
    if request.method == 'POST' and form.is_valid():
        paciente = form.save(commit=False)
        paciente.origen = _origen(request, paciente)
        paciente.registrado_por = request.user
        paciente.save()
        messages.success(request, f"Paciente registrado con N° de Historia {paciente.numero_historia}.")
        if request.POST.get('siguiente') == 'cita':
            return redirect(f"{reverse('nueva_cita')}?dni={paciente.dni}")
        return redirect('lista_pacientes')
    return render(request, 'admision/pacientes/form.html', {'form': form})


# ---------- Citas (HU-08 a HU-12) ----------

@rol_requerido(*RECEPCION)
def nueva_cita(request):
    inicial = {'paciente_dni': request.GET.get('dni', ''), 'fecha': request.GET.get('fecha', ''),
               'hora': request.GET.get('hora', ''), 'medico': request.GET.get('medico', '')}
    form = CitaForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        cita = form.save(commit=False)
        cita.creado_por = request.user
        try:
            with transaction.atomic():
                cita.save()
        except IntegrityError:
            form.add_error('hora', 'Ese turno acaba de ser tomado. Elige otro horario.')
        else:
            messages.success(request, f"Cita agendada: {cita}.")
            return redirect(f"{reverse('agenda')}?fecha={cita.fecha.isoformat()}")
    return render(request, 'admision/citas/form.html', {'form': form})


@require_GET
@rol_requerido(*RECEPCION)
def api_disponibilidad(request):
    medico = Usuario.objects.filter(pk=request.GET.get('medico'), rol=Usuario.MEDICO).first()
    fecha = _fecha_param(request.GET.get('fecha'))
    if not medico:
        return JsonResponse({'turnos': []})
    excluir = Cita.objects.filter(pk=request.GET.get('excluir')).first() if request.GET.get('excluir') else None
    turnos = [t.strftime('%H:%M') for t in turnos_disponibles(medico, fecha, excluir)]
    return JsonResponse({'turnos': turnos})


@rol_requerido(*AGENDA)
def agenda(request):
    """HU-09: citas del día filtradas por fecha y estado."""
    fecha = _fecha_param(request.GET.get('fecha'))
    estado = request.GET.get('estado', '')
    citas = Cita.objects.del_dia(fecha).select_related('paciente', 'medico', 'atencion')
    if request.user.rol == Usuario.MEDICO and not request.user.es_admin:
        citas = citas.filter(medico=request.user)
    elif request.GET.get('medico'):
        citas = citas.filter(medico_id=request.GET['medico'])
    filtros = [(clave, nombre, citas.filter(estado=clave).count()) for clave, nombre in Cita.ESTADOS]
    if estado:
        citas = citas.filter(estado=estado)
    return render(request, 'admision/citas/agenda.html', {
        'citas': citas, 'fecha': fecha, 'estado': estado, 'filtros': filtros,
        'medicos': medicos_activos(), 'medico_sel': request.GET.get('medico', ''),
        'anterior': fecha - timedelta(days=1), 'siguiente': fecha + timedelta(days=1),
        'es_hoy': fecha == timezone.localdate(),
    })


@rol_requerido(*AGENDA)
def calendario(request):
    """HU-08: calendario semanal interactivo por médico."""
    medicos = medicos_activos()
    medico = medicos.filter(pk=request.GET.get('medico')).first() or medicos.first()
    if request.user.rol == Usuario.MEDICO and not request.user.es_admin:
        medico = request.user
    base = _fecha_param(request.GET.get('semana'))
    lunes = base - timedelta(days=base.weekday())
    dias = [lunes + timedelta(days=i) for i in range(7)]
    citas = {}
    if medico:
        for c in Cita.objects.activas().filter(medico=medico, fecha__range=(dias[0], dias[-1])).select_related('paciente'):
            citas[(c.fecha, c.hora)] = c
    ahora = timezone.localtime().replace(tzinfo=None)
    filas = [{
        'hora': t,
        'celdas': [{'fecha': d, 'cita': citas.get((d, t)), 'pasado': datetime.combine(d, t) <= ahora} for d in dias],
    } for t in turnos_del_dia()]
    return render(request, 'admision/citas/calendario.html', {
        'medicos': medicos, 'medico': medico, 'dias': dias, 'filas': filas,
        'semana_anterior': lunes - timedelta(days=7), 'semana_siguiente': lunes + timedelta(days=7),
    })


def _volver_agenda(cita):
    return redirect(f"{reverse('agenda')}?fecha={cita.fecha.isoformat()}")


@require_POST
@rol_requerido(*RECEPCION)
def reprogramar_cita(request, pk):
    """HU-10: cambio de fecha/hora con revalidación de disponibilidad."""
    cita = get_object_or_404(Cita, pk=pk)
    if cita.estado != Cita.AGENDADA:
        messages.error(request, "Solo se pueden reprogramar citas en estado Agendada.")
        return _volver_agenda(cita)
    form = ReprogramarForm(request.POST, instance=cita)
    if form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            messages.error(request, "Ese turno acaba de ser tomado. Elige otro horario.")
        else:
            messages.success(request, f"Cita reprogramada para el {cita.fecha:%d/%m/%Y} a las {cita.hora:%H:%M}.")
    else:
        cita.refresh_from_db()
        errores = '; '.join(e for lista in form.errors.values() for e in lista)
        messages.error(request, f"No se pudo reprogramar: {errores}")
    return _volver_agenda(cita)


@require_POST
@rol_requerido(*RECEPCION)
def cancelar_cita(request, pk):
    """HU-11: cancelación con motivo obligatorio; libera el turno."""
    cita = get_object_or_404(Cita, pk=pk)
    form = CancelarForm(request.POST)
    if not cita.editable:
        messages.error(request, "Esta cita ya no se puede cancelar.")
    elif form.is_valid():
        cita.estado = Cita.CANCELADA
        cita.motivo_cancelacion = form.cleaned_data['motivo_cancelacion']
        cita.save(update_fields=['estado', 'motivo_cancelacion', 'actualizado_en'])
        messages.success(request, f"Cita de {cita.paciente.nombre_completo} cancelada. El turno quedó libre.")
    else:
        messages.error(request, "Debes indicar el motivo de la cancelación.")
    return _volver_agenda(cita)


@require_POST
@rol_requerido(*RECEPCION)
def confirmar_llegada(request, pk):
    """HU-12: el paciente pasa a 'En espera' y se notifica al médico."""
    cita = get_object_or_404(Cita, pk=pk)
    if cita.estado != Cita.AGENDADA:
        messages.error(request, "Solo se puede confirmar la llegada de citas agendadas.")
    elif cita.fecha != timezone.localdate():
        messages.error(request, "Solo se confirma la llegada de citas del día.")
    else:
        cita.estado = Cita.EN_ESPERA
        cita.llegada_en = timezone.now()
        cita.save(update_fields=['estado', 'llegada_en', 'actualizado_en'])
        messages.success(request, f"{cita.paciente.nombre_completo} está en sala de espera.")
    return _volver_agenda(cita)


@require_GET
@rol_requerido(Usuario.MEDICO)
def api_en_espera(request):
    """HU-12: notificación en la pantalla del médico (consultada periódicamente)."""
    citas = (Cita.objects.del_dia(timezone.localdate()).filter(estado=Cita.EN_ESPERA, medico=request.user)
             .select_related('paciente').order_by('llegada_en'))
    return JsonResponse({'pacientes': [{
        'id': c.pk, 'paciente': c.paciente.nombre_completo, 'hora': c.hora.strftime('%H:%M'),
        'llegada': timezone.localtime(c.llegada_en).strftime('%H:%M') if c.llegada_en else '',
    } for c in citas]})
