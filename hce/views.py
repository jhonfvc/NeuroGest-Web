import json

from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from admision.models import Cita, Paciente
from seguridad.models import Usuario
from seguridad.permisos import acceso_denegado, rol_requerido

from .forms import AtencionForm, PrescripcionFormSet, TriajeForm
from .models import Atencion, Cie10, Diagnostico, Prescripcion

MIN_CARACTERES = 3


def _buscar_pacientes(q):
    """HU-13: búsqueda por DNI, apellidos, nombres o N° de historia (usa los índices por DNI y apellidos)."""
    filtro = Q(dni__startswith=q) | Q(numero_historia__iexact=q)
    for palabra in q.split():
        filtro |= Q(apellido_paterno__istartswith=palabra) | Q(apellido_materno__istartswith=palabra) | Q(nombres__istartswith=palabra)
    return (Paciente.objects.filter(filtro).annotate(ultima_atencion=Max('atenciones__fecha'))
            .order_by('apellido_paterno', 'apellido_materno', 'nombres')[:20])


@rol_requerido(Usuario.MEDICO)
def buscar(request):
    q = request.GET.get('q', '').strip()
    pacientes = _buscar_pacientes(q) if len(q) >= MIN_CARACTERES else []
    return render(request, 'hce/buscar.html', {'q': q, 'pacientes': pacientes, 'min': MIN_CARACTERES})


@require_GET
@rol_requerido(Usuario.MEDICO)
def api_buscar(request):
    q = request.GET.get('q', '').strip()
    if len(q) < MIN_CARACTERES:
        return JsonResponse({'resultados': []})
    return JsonResponse({'resultados': [{
        'id': p.pk, 'dni': p.dni, 'nombre': p.nombre_completo, 'numero_historia': p.numero_historia,
        'edad': p.edad, 'ultima_atencion': p.ultima_atencion.strftime('%d/%m/%Y') if p.ultima_atencion else None,
    } for p in _buscar_pacientes(q)]})


@rol_requerido(Usuario.MEDICO)
def expediente(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk)
    proxima = paciente.citas.activas().filter(estado__in=[Cita.AGENDADA, Cita.EN_ESPERA]).order_by('fecha', 'hora').first()
    return render(request, 'hce/expediente.html', {
        'paciente': paciente, 'total_atenciones': paciente.atenciones.count(), 'proxima': proxima,
    })


@require_GET
@rol_requerido(Usuario.MEDICO)
def historial(request, pk):
    """HU-14: línea de tiempo (cargada de forma asíncrona), de la más reciente a la más antigua."""
    paciente = get_object_or_404(Paciente, pk=pk)
    atenciones = (paciente.atenciones.select_related('medico', 'triaje')
                  .prefetch_related('diagnosticos__cie10', 'prescripciones').order_by('-fecha'))
    return render(request, 'hce/_historial.html', {'atenciones': atenciones})


@require_GET
@rol_requerido(Usuario.MEDICO)
def api_cie10(request):
    """HU-17: autocompletado por código o descripción."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'resultados': []})
    resultados = Cie10.objects.filter(Q(codigo__istartswith=q) | Q(descripcion__icontains=q))[:15]
    return JsonResponse({'resultados': [{'id': c.pk, 'codigo': c.codigo, 'descripcion': c.descripcion} for c in resultados]})


def nueva_atencion(request, paciente_pk=None, cita_pk=None):
    """HU-15 a HU-18: triaje, evolución, diagnóstico CIE-10 y receta en una sola ficha."""
    if request.user.rol != Usuario.MEDICO:
        return acceso_denegado(request)
    cita = None
    if cita_pk:
        cita = get_object_or_404(Cita.objects.select_related('paciente'), pk=cita_pk, medico=request.user)
        if cita.estado != Cita.EN_ESPERA:
            messages.error(request, 'Solo se atienden citas con el paciente en sala de espera.')
            return redirect('agenda')
        paciente = cita.paciente
    else:
        paciente = get_object_or_404(Paciente, pk=paciente_pk)

    datos = request.POST if request.method == 'POST' else None
    form = AtencionForm(datos, initial={'motivo_consulta': cita.motivo if cita else ''})
    triaje_form = TriajeForm(datos, prefix='triaje')
    recetas = PrescripcionFormSet(datos, prefix='receta')

    if request.method == 'POST' and all([form.is_valid(), triaje_form.is_valid(), recetas.is_valid()]):
        with transaction.atomic():
            atencion = form.save(commit=False)
            atencion.paciente, atencion.medico, atencion.cita = paciente, request.user, cita
            atencion.save()
            triaje = triaje_form.save(commit=False)
            triaje.atencion = atencion
            triaje.save()
            Diagnostico.objects.bulk_create([
                Diagnostico(atencion=atencion, cie10=c, principal=(i == 0))
                for i, c in enumerate(form.cleaned_data['diagnosticos'])
            ])
            recetas.instance = atencion
            recetas.save()
            if cita:
                cita.estado = Cita.ATENDIDA
                cita.save(update_fields=['estado', 'actualizado_en'])
        messages.success(request, 'Atención registrada en la historia clínica.')
        return redirect('detalle_atencion', pk=atencion.pk)

    seleccionados = []
    if form.is_bound and 'diagnosticos' in form.cleaned_data:
        seleccionados = form.cleaned_data['diagnosticos']
    elif form.is_bound:
        ids = [int(i) for i in request.POST.get('diagnosticos', '').split(',') if i.strip().isdigit()]
        seleccionados = list(Cie10.objects.filter(pk__in=ids))
    return render(request, 'hce/atencion_form.html', {
        'paciente': paciente, 'cita': cita, 'form': form, 'triaje_form': triaje_form, 'recetas': recetas,
        'seleccionados_json': [{'id': c.pk, 'codigo': c.codigo, 'descripcion': c.descripcion} for c in seleccionados],
        'dosis_maxima': json.dumps(Prescripcion.DOSIS_MAXIMA),
        'ultima': paciente.atenciones.select_related('triaje').first(),
    })


@rol_requerido(Usuario.MEDICO)
def detalle_atencion(request, pk):
    atencion = get_object_or_404(
        Atencion.objects.select_related('paciente', 'medico', 'triaje').prefetch_related('diagnosticos__cie10', 'prescripciones'),
        pk=pk)
    return render(request, 'hce/atencion_detalle.html', {'atencion': atencion})
