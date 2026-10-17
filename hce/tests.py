from datetime import time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from admision.models import Cita, Paciente
from seguridad.models import Usuario

from .models import Atencion, Cie10, Prescripcion, Triaje

CLAVE = 'ClaveSegura#2026'


def usuario(username, rol):
    return Usuario.objects.create_user(username, email=f'{username}@neurogest.pe', password=CLAVE, rol=rol)


def paciente(dni, nombres, paterno, materno=''):
    return Paciente.objects.create(dni=dni, nombres=nombres, apellido_paterno=paterno, apellido_materno=materno)


def datos_atencion(diagnosticos, medicamentos=(), **cambios):
    datos = {
        'motivo_consulta': 'Cefalea pulsátil de 3 días', 'evolucion': 'Paciente estable',
        'anamnesis': 'Sin antecedentes', 'diagnosticos': ','.join(str(d.pk) for d in diagnosticos),
        'triaje-presion_sistolica': '120', 'triaje-presion_diastolica': '80',
        'triaje-peso': '70', 'triaje-talla': '175',
        'receta-TOTAL_FORMS': str(len(medicamentos)), 'receta-INITIAL_FORMS': '0',
        'receta-MIN_NUM_FORMS': '0', 'receta-MAX_NUM_FORMS': '15',
    }
    for i, med in enumerate(medicamentos):
        for campo, valor in med.items():
            datos[f'receta-{i}-{campo}'] = valor
    datos.update(cambios)
    return datos


PARACETAMOL = {'medicamento': 'Paracetamol', 'presentacion': '500 mg tab', 'dosis': '500', 'unidad': 'mg',
               'via': 'VO', 'frecuencia_horas': '8', 'duracion_dias': '3'}


class BaseHce(TestCase):
    def setUp(self):
        self.medico = usuario('medico', Usuario.MEDICO)
        self.recep = usuario('recep', Usuario.RECEPCION)
        self.p1 = paciente('12345678', 'Rosa', 'Quispe', 'Mamani')
        self.p2 = paciente('87654321', 'Luis', 'Torres', 'Vega')
        self.migrana = Cie10.objects.get(codigo='G43.9')
        self.cefalea = Cie10.objects.get(codigo='R51')
        self.client.force_login(self.medico)

    def cita_en_espera(self, pac=None):
        return Cita.objects.create(paciente=pac or self.p1, medico=self.medico, fecha=timezone.localdate(),
                                   hora=time(9), estado=Cita.EN_ESPERA, motivo='Cefalea')


class BusquedaExpedienteTests(BaseHce):
    """HU-13: búsqueda por DNI/apellidos desde 3 caracteres."""

    def buscar(self, q):
        return self.client.get(reverse('api_buscar_expediente'), {'q': q}).json()['resultados']

    def test_busca_por_dni(self):
        self.assertEqual([r['dni'] for r in self.buscar('123')], ['12345678'])

    def test_busca_por_apellido(self):
        self.assertEqual([r['dni'] for r in self.buscar('torr')], ['87654321'])

    def test_busca_por_numero_de_historia(self):
        self.assertEqual(len(self.buscar(self.p2.numero_historia)), 1)

    def test_minimo_tres_caracteres(self):
        self.assertEqual(self.buscar('to'), [])

    def test_muestra_numero_de_historia(self):
        self.assertEqual(self.buscar('quispe')[0]['numero_historia'], self.p1.numero_historia)

    def test_recepcion_no_accede_a_hce(self):
        self.client.force_login(self.recep)
        self.assertEqual(self.client.get(reverse('buscar_expediente')).status_code, 403)
        self.assertEqual(self.client.get(reverse('expediente', args=[self.p1.pk])).status_code, 403)

    def test_busqueda_sin_js(self):
        resp = self.client.get(reverse('buscar_expediente'), {'q': 'quispe'})
        self.assertContains(resp, 'Rosa Quispe Mamani')


class HistorialTests(BaseHce):
    """HU-14: línea de tiempo de atenciones, de la más reciente a la más antigua."""

    def test_historial_ordenado(self):
        primera = Atencion.objects.create(paciente=self.p1, medico=self.medico, motivo_consulta='Primera', evolucion='-')
        segunda = Atencion.objects.create(paciente=self.p1, medico=self.medico, motivo_consulta='Segunda', evolucion='-')
        Atencion.objects.filter(pk=primera.pk).update(fecha=timezone.now() - timezone.timedelta(days=30))
        resp = self.client.get(reverse('historial', args=[self.p1.pk]))
        self.assertEqual(list(resp.context['atenciones']), [segunda, primera])

    def test_expediente_carga_historial_asincrono(self):
        resp = self.client.get(reverse('expediente', args=[self.p1.pk]))
        self.assertContains(resp, reverse('historial', args=[self.p1.pk]))


class TriajeTests(TestCase):
    """HU-15: cálculo automático de IMC."""

    def test_calculo_imc(self):
        self.assertEqual(Triaje.calcular_imc(Decimal('70'), Decimal('175')), Decimal('22.86'))

    def test_clasificacion(self):
        triaje = Triaje(imc=Decimal('31'))
        self.assertEqual(triaje.clasificacion_imc, 'Obesidad')


class RegistroAtencionTests(BaseHce):
    """HU-15 a HU-18: registro completo de la atención."""

    def test_registra_atencion_desde_cita(self):
        cita = self.cita_en_espera()
        resp = self.client.post(reverse('nueva_atencion', args=[cita.pk]),
                                datos_atencion([self.migrana, self.cefalea], [PARACETAMOL]))
        atencion = Atencion.objects.get()
        self.assertRedirects(resp, reverse('detalle_atencion', args=[atencion.pk]))
        self.assertEqual(atencion.triaje.imc, Decimal('22.86'))
        self.assertEqual(atencion.diagnostico_principal.cie10, self.migrana)
        self.assertEqual(atencion.diagnosticos.count(), 2)
        self.assertEqual(atencion.prescripciones.get().medicamento, 'Paracetamol')
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.ATENDIDA)
        self.assertEqual(atencion.cita, cita)

    def test_triaje_obligatorio(self):
        cita = self.cita_en_espera()
        resp = self.client.post(reverse('nueva_atencion', args=[cita.pk]),
                                datos_atencion([self.migrana], **{'triaje-peso': ''}))
        self.assertIn('peso', resp.context['triaje_form'].errors)
        self.assertFalse(Atencion.objects.exists())

    def test_diastolica_menor_que_sistolica(self):
        resp = self.client.post(reverse('nueva_atencion_paciente', args=[self.p1.pk]),
                                datos_atencion([self.migrana], **{'triaje-presion_diastolica': '130'}))
        self.assertIn('presion_diastolica', resp.context['triaje_form'].errors)

    def test_campos_obligatorios_de_evolucion(self):
        resp = self.client.post(reverse('nueva_atencion_paciente', args=[self.p1.pk]),
                                datos_atencion([self.migrana], motivo_consulta='', evolucion=''))
        self.assertIn('motivo_consulta', resp.context['form'].errors)
        self.assertIn('evolucion', resp.context['form'].errors)

    def test_diagnostico_obligatorio(self):
        resp = self.client.post(reverse('nueva_atencion_paciente', args=[self.p1.pk]), datos_atencion([]))
        self.assertIn('diagnosticos', resp.context['form'].errors)
        self.assertFalse(Atencion.objects.exists())

    def test_atencion_sin_receta(self):
        self.client.post(reverse('nueva_atencion_paciente', args=[self.p1.pk]), datos_atencion([self.migrana]))
        self.assertEqual(Atencion.objects.get().prescripciones.count(), 0)

    def test_atencion_es_inmutable(self):
        atencion = Atencion.objects.create(paciente=self.p1, medico=self.medico, motivo_consulta='x', evolucion='y')
        atencion.evolucion = 'cambiado'
        with self.assertRaises(ValidationError):
            atencion.save()

    def test_solo_citas_en_espera_del_propio_medico(self):
        otro = usuario('medico2', Usuario.MEDICO)
        cita = Cita.objects.create(paciente=self.p1, medico=otro, fecha=timezone.localdate(), hora=time(9), estado=Cita.EN_ESPERA)
        self.assertEqual(self.client.get(reverse('nueva_atencion', args=[cita.pk])).status_code, 404)
        agendada = Cita.objects.create(paciente=self.p2, medico=self.medico, fecha=timezone.localdate(), hora=time(10))
        self.assertRedirects(self.client.get(reverse('nueva_atencion', args=[agendada.pk])), reverse('agenda'))

    def test_recepcion_no_registra_atenciones(self):
        self.client.force_login(self.recep)
        self.assertEqual(self.client.get(reverse('nueva_atencion_paciente', args=[self.p1.pk])).status_code, 403)

    def test_formulario_se_muestra(self):
        cita = self.cita_en_espera()
        resp = self.client.get(reverse('nueva_atencion', args=[cita.pk]))
        self.assertContains(resp, 'Triaje y funciones vitales')
        self.assertEqual(resp.context['form'].initial['motivo_consulta'], 'Cefalea')


class Cie10Tests(BaseHce):
    """HU-17: autocompletado CIE-10 por código o descripción."""

    def buscar(self, q):
        return [r['codigo'] for r in self.client.get(reverse('api_cie10'), {'q': q}).json()['resultados']]

    def test_por_codigo(self):
        self.assertIn('G43.9', self.buscar('G43'))

    def test_por_descripcion(self):
        self.assertIn('G43.0', self.buscar('migraña'))

    def test_catalogo_base_cargado(self):
        self.assertGreaterEqual(Cie10.objects.count(), 70)


class PrescripcionTests(BaseHce):
    """HU-18 / HU-NF09: validación de dosis y campos numéricos."""

    def test_rechaza_dosis_sobre_el_maximo(self):
        med = dict(PARACETAMOL, dosis='5000')
        resp = self.client.post(reverse('nueva_atencion_paciente', args=[self.p1.pk]), datos_atencion([self.migrana], [med]))
        self.assertIn('dosis', resp.context['recetas'].forms[0].errors)
        self.assertFalse(Atencion.objects.exists())

    def test_rechaza_dosis_cero_y_frecuencia_invalida(self):
        med = dict(PARACETAMOL, dosis='0', frecuencia_horas='0')
        resp = self.client.post(reverse('nueva_atencion_paciente', args=[self.p1.pk]), datos_atencion([self.migrana], [med]))
        errores = resp.context['recetas'].forms[0].errors
        self.assertIn('dosis', errores)
        self.assertIn('frecuencia_horas', errores)

    def test_posologia(self):
        p = Prescripcion(medicamento='Paracetamol', dosis=Decimal('500.00'), unidad='mg', via='VO', frecuencia_horas=8, duracion_dias=3)
        self.assertEqual(p.posologia, '500 mg vía oral cada 8 h por 3 día(s)')
