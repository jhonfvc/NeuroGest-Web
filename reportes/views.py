from datetime import date

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from admision.forms import medicos_activos
from hce.models import Atencion
from seguridad.models import Usuario
from seguridad.permisos import rol_requerido

from .documentos import receta_pdf, reporte_excel, reporte_pdf
from .servicios import generar_resumen


def _fecha(valor, defecto):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return defecto


def _resumen_desde(request):
    hoy = timezone.localdate()
    inicio = _fecha(request.GET.get('inicio'), hoy.replace(day=1))
    fin = _fecha(request.GET.get('fin'), hoy)
    medico = Usuario.objects.filter(pk=request.GET.get('medico'), rol=Usuario.MEDICO).first() if request.GET.get('medico') else None
    return generar_resumen(inicio, fin, medico)


def _descarga(contenido, tipo, nombre):
    resp = HttpResponse(contenido, content_type=tipo)
    resp['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return resp


@rol_requerido(Usuario.ADMIN)
def panel(request):
    """HU-20: gráficos y tabla de citas atendidas, canceladas y ausentes por rango de fecha."""
    resumen = _resumen_desde(request)
    return render(request, 'reportes/panel.html', {
        'resumen': resumen, 'medicos': medicos_activos(), 'medico_sel': request.GET.get('medico', ''),
        'serie': [{'fecha': d['fecha'].strftime('%d/%m'), 'atendidas': d['atendidas'], 'canceladas': d['canceladas'],
                   'ausentes': d['ausentes']} for d in resumen.por_dia],
        'consulta': request.GET.urlencode(),
    })


@rol_requerido(Usuario.ADMIN)
def exportar_excel(request):
    resumen = _resumen_desde(request)
    return _descarga(reporte_excel(resumen),
                     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     f'reporte_atenciones_{resumen.inicio:%Y%m%d}_{resumen.fin:%Y%m%d}.xlsx')


@rol_requerido(Usuario.ADMIN)
def exportar_pdf(request):
    resumen = _resumen_desde(request)
    return _descarga(reporte_pdf(resumen), 'application/pdf',
                     f'reporte_atenciones_{resumen.inicio:%Y%m%d}_{resumen.fin:%Y%m%d}.pdf')


@rol_requerido(Usuario.MEDICO)
def descargar_receta(request, pk):
    """HU-19: receta en PDF en 1 clic."""
    atencion = get_object_or_404(Atencion.objects.select_related('paciente', 'medico', 'triaje'), pk=pk)
    resp = HttpResponse(receta_pdf(atencion), content_type='application/pdf')
    disposicion = 'attachment' if request.GET.get('descargar') else 'inline'
    resp['Content-Disposition'] = f'{disposicion}; filename="receta_{atencion.paciente.numero_historia}_{atencion.fecha:%Y%m%d}.pdf"'
    return resp
