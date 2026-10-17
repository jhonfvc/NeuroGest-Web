from datetime import time, timedelta
from unittest import mock

import requests
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from seguridad.models import Usuario

from . import reniec
from .models import Cita, Paciente, turnos_disponibles

CLAVE = 'ClaveSegura#2026'
API = {'RENIEC_API_URL': 'https://api.prueba.pe/dni', 'RENIEC_API_TOKEN': 'token-prueba'}


def usuario(username, rol, **extra):
    return Usuario.objects.create_user(username, email=f'{username}@neurogest.pe', password=CLAVE, rol=rol,
                                       first_name=username.title(), **extra)


def paciente(dni='12345678', **extra):
    datos = {'nombres': 'Rosa', 'apellido_paterno': 'Quispe', 'apellido_materno': 'Mamani'}
    datos.update(extra)
    return Paciente.objects.create(dni=dni, **datos)


def manana():
    return timezone.localdate() + timedelta(days=1)


def respuesta(status=200, datos=None):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = datos or {}
    resp.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(str(status))
    return resp


RENIEC_OK = {'nombres': 'ROSA MARIA', 'apellidoPaterno': 'QUISPE', 'apellidoMaterno': 'MAMANI'}


class BaseTest(TestCase):
    def setUp(self):
        self.recep = usuario('recep', Usuario.RECEPCION)
        self.medico = usuario('medico', Usuario.MEDICO)
        self.medico2 = usuario('medico2', Usuario.MEDICO)
        self.client.force_login(self.recep)


@override_settings(**API)
class ClienteReniecTests(TestCase):
    """HU-06: cliente HTTP con timeout global de 3 s y 2 reintentos."""

    @mock.patch('admision.reniec.requests.get', return_value=respuesta(datos=RENIEC_OK))
    def test_consulta_exitosa(self, get):
        datos = reniec.consultar_dni('12345678')
        self.assertEqual((datos.nombres, datos.apellido_paterno), ('Rosa Maria', 'Quispe'))
        self.assertLessEqual(get.call_args.kwargs['timeout'], reniec.TIEMPO_TOTAL)

    @mock.patch('admision.reniec.time.sleep')
    @mock.patch('admision.reniec.requests.get')
    def test_reintenta_y_luego_responde(self, get, _sleep):
        get.side_effect = [requests.Timeout(), requests.ConnectionError(), respuesta(datos=RENIEC_OK)]
        self.assertEqual(reniec.consultar_dni('12345678').nombres, 'Rosa Maria')
        self.assertEqual(get.call_count, 3)

    @mock.patch('admision.reniec.time.sleep')
    @mock.patch('admision.reniec.requests.get', side_effect=requests.Timeout())
    def test_maximo_dos_reintentos(self, get, _sleep):
        with self.assertRaises(reniec.ReniecNoDisponible):
            reniec.consultar_dni('12345678')
        self.assertEqual(get.call_count, 1 + reniec.REINTENTOS)

    @mock.patch('admision.reniec.requests.get', return_value=respuesta(status=404))
    def test_dni_inexistente(self, _get):
        with self.assertRaises(reniec.DniNoEncontrado):
            reniec.consultar_dni('12345678')

    @override_settings(RENIEC_API_TOKEN='')
    def test_sin_token_no_disponible(self):
        with self.assertRaises(reniec.ReniecNoDisponible):
            reniec.consultar_dni('12345678')

    def test_formato_alternativo_del_proveedor(self):
        datos = reniec._interpretar('12345678', {'first_name': 'ANA', 'first_last_name': 'RIOS', 'second_last_name': 'PAZ'})
        self.assertEqual(datos.apellido_materno, 'Paz')


@override_settings(**API)
class AdmisionTests(BaseTest):
    """HU-06 y HU-07: autocompletado y registro manual de contingencia."""

    def datos_form(self, **cambios):
        datos = {'dni': '12345678', 'nombres': 'Rosa Maria', 'apellido_paterno': 'Quispe',
                 'apellido_materno': 'Mamani', 'telefono': '987654321'}
        datos.update(cambios)
        return datos

    @mock.patch('admision.reniec.requests.get', return_value=respuesta(datos=RENIEC_OK))
    def test_autocompletado_y_origen_api(self, _get):
        resp = self.client.get(reverse('api_consulta_dni', args=['12345678']))
        self.assertTrue(resp.json()['ok'])
        self.client.post(reverse('registrar_paciente'), self.datos_form())
        p = Paciente.objects.get(dni='12345678')
        self.assertEqual(p.origen, Paciente.API)
        self.assertEqual(p.registrado_por, self.recep)
        self.assertEqual(p.numero_historia, 'HC-000001')

    @mock.patch('admision.reniec.requests.get', return_value=respuesta(datos=RENIEC_OK))
    def test_datos_modificados_se_registran_como_manual(self, _get):
        self.client.get(reverse('api_consulta_dni', args=['12345678']))
        self.client.post(reverse('registrar_paciente'), self.datos_form(nombres='Otro Nombre'))
        self.assertEqual(Paciente.objects.get(dni='12345678').origen, Paciente.MANUAL)

    @mock.patch('admision.reniec.time.sleep')
    @mock.patch('admision.reniec.requests.get', side_effect=requests.Timeout())
    def test_api_caida_activa_modo_manual(self, _get, _sleep):
        resp = self.client.get(reverse('api_consulta_dni', args=['12345678']))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['modo'], 'manual')
        self.client.post(reverse('registrar_paciente'), self.datos_form())
        self.assertEqual(Paciente.objects.get(dni='12345678').origen, Paciente.MANUAL)

    def test_dni_ya_registrado(self):
        paciente()
        resp = self.client.get(reverse('api_consulta_dni', args=['12345678']))
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(resp.json()['existe'])

    def test_dni_invalido(self):
        self.assertEqual(self.client.get(reverse('api_consulta_dni', args=['1234'])).status_code, 400)

    def test_no_permite_dni_duplicado(self):
        paciente()
        resp = self.client.post(reverse('registrar_paciente'), self.datos_form())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Paciente.objects.count(), 1)

    def test_guardar_y_agendar_redirige_a_nueva_cita(self):
        resp = self.client.post(reverse('registrar_paciente'), self.datos_form(siguiente='cita'))
        self.assertRedirects(resp, f"{reverse('nueva_cita')}?dni=12345678")

    def test_busqueda_de_pacientes(self):
        paciente()
        paciente('87654321', nombres='Luis', apellido_paterno='Torres')
        resp = self.client.get(reverse('lista_pacientes'), {'q': 'torres'})
        self.assertEqual([p.dni for p in resp.context['pacientes']], ['87654321'])

    def test_medico_no_accede_a_admision(self):
        self.client.force_login(self.medico)
        self.assertEqual(self.client.get(reverse('registrar_paciente')).status_code, 403)


class AgendamientoTests(BaseTest):
    """HU-08: agendamiento sin cruce de horarios."""

    def setUp(self):
        super().setUp()
        self.paciente = paciente()

    def agendar(self, **cambios):
        datos = {'paciente_dni': '12345678', 'medico': self.medico.pk, 'fecha': manana().isoformat(),
                 'hora': '09:00', 'motivo': 'Cefalea'}
        datos.update(cambios)
        return self.client.post(reverse('nueva_cita'), datos)

    def test_agenda_cita_en_estado_agendada(self):
        self.agendar()
        cita = Cita.objects.get()
        self.assertEqual(cita.estado, Cita.AGENDADA)
        self.assertEqual(cita.creado_por, self.recep)

    def test_bloquea_cruce_de_horario(self):
        self.agendar()
        otro = paciente('87654321')
        resp = self.agendar(paciente_dni=otro.dni)
        self.assertIn('El médico ya tiene una cita en ese horario.', resp.context['form'].errors['hora'])
        self.assertEqual(Cita.objects.count(), 1)

    def test_otro_medico_mismo_horario(self):
        self.agendar()
        self.agendar(medico=self.medico2.pk)
        self.assertEqual(Cita.objects.count(), 2)

    def test_no_permite_fecha_pasada(self):
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        resp = self.agendar(fecha=ayer)
        self.assertIn('fecha', resp.context['form'].errors)

    def test_paciente_no_registrado(self):
        resp = self.agendar(paciente_dni='99999999')
        self.assertIn('paciente_dni', resp.context['form'].errors)

    def test_restriccion_en_bd_ante_concurrencia(self):
        Cita.objects.create(paciente=self.paciente, medico=self.medico, fecha=manana(), hora=time(9))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cita.objects.create(paciente=paciente('87654321'), medico=self.medico, fecha=manana(), hora=time(9))

    def test_turno_cancelado_puede_reutilizarse(self):
        Cita.objects.create(paciente=self.paciente, medico=self.medico, fecha=manana(), hora=time(9), estado=Cita.CANCELADA)
        self.agendar()
        self.assertEqual(Cita.objects.activas().count(), 1)

    def test_turnos_fuera_de_horario(self):
        cita = Cita(paciente=self.paciente, medico=self.medico, fecha=manana(), hora=time(20))
        with self.assertRaises(ValidationError):
            cita.full_clean()

    def test_disponibilidad_excluye_turnos_ocupados(self):
        Cita.objects.create(paciente=self.paciente, medico=self.medico, fecha=manana(), hora=time(9))
        resp = self.client.get(reverse('api_disponibilidad'), {'medico': self.medico.pk, 'fecha': manana().isoformat()})
        turnos = resp.json()['turnos']
        self.assertNotIn('09:00', turnos)
        self.assertIn('09:30', turnos)
        self.assertEqual(len(turnos), 23)

    def test_calendario_semanal(self):
        Cita.objects.create(paciente=self.paciente, medico=self.medico, fecha=manana(), hora=time(9))
        resp = self.client.get(reverse('calendario'), {'medico': self.medico.pk, 'semana': manana().isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Quispe')


class AgendaYEstadosTests(BaseTest):
    """HU-09 a HU-12: agenda diaria, reprogramación, cancelación y llegada."""

    def setUp(self):
        super().setUp()
        self.paciente = paciente()
        self.hoy = timezone.localdate()
        self.cita_hoy = Cita.objects.create(paciente=self.paciente, medico=self.medico, fecha=self.hoy, hora=time(10))
        self.cita_manana = Cita.objects.create(paciente=self.paciente, medico=self.medico, fecha=manana(), hora=time(9))
        Cita.objects.create(paciente=paciente('87654321'), medico=self.medico2, fecha=self.hoy, hora=time(11))

    # HU-09
    def test_agenda_filtra_por_fecha(self):
        resp = self.client.get(reverse('agenda'))
        self.assertEqual(len(resp.context['citas']), 2)
        resp = self.client.get(reverse('agenda'), {'fecha': manana().isoformat()})
        self.assertEqual(list(resp.context['citas']), [self.cita_manana])

    def test_agenda_filtra_por_estado(self):
        resp = self.client.get(reverse('agenda'), {'estado': Cita.EN_ESPERA})
        self.assertEqual(len(resp.context['citas']), 0)

    def test_medico_solo_ve_sus_citas(self):
        self.client.force_login(self.medico)
        resp = self.client.get(reverse('agenda'))
        self.assertEqual(list(resp.context['citas']), [self.cita_hoy])

    # HU-10
    def test_reprogramar(self):
        self.client.post(reverse('reprogramar_cita', args=[self.cita_manana.pk]),
                         {'fecha': manana().isoformat(), 'hora': '15:00'})
        self.cita_manana.refresh_from_db()
        self.assertEqual(self.cita_manana.hora, time(15))

    def test_reprogramar_a_turno_ocupado(self):
        Cita.objects.create(paciente=paciente('11112222'), medico=self.medico, fecha=manana(), hora=time(15))
        self.client.post(reverse('reprogramar_cita', args=[self.cita_manana.pk]),
                         {'fecha': manana().isoformat(), 'hora': '15:00'})
        self.cita_manana.refresh_from_db()
        self.assertEqual(self.cita_manana.hora, time(9))

    def test_disponibilidad_al_reprogramar_incluye_su_propio_turno(self):
        resp = self.client.get(reverse('api_disponibilidad'), {
            'medico': self.medico.pk, 'fecha': manana().isoformat(), 'excluir': self.cita_manana.pk})
        self.assertIn('09:00', resp.json()['turnos'])

    # HU-11
    def test_cancelar_exige_motivo(self):
        self.client.post(reverse('cancelar_cita', args=[self.cita_manana.pk]), {'motivo_cancelacion': ''})
        self.cita_manana.refresh_from_db()
        self.assertEqual(self.cita_manana.estado, Cita.AGENDADA)

    def test_cancelar_libera_el_turno(self):
        self.client.post(reverse('cancelar_cita', args=[self.cita_manana.pk]), {'motivo_cancelacion': 'Viaje del paciente'})
        self.cita_manana.refresh_from_db()
        self.assertEqual(self.cita_manana.estado, Cita.CANCELADA)
        self.assertEqual(self.cita_manana.motivo_cancelacion, 'Viaje del paciente')
        self.assertIn(time(9), turnos_disponibles(self.medico, manana()))

    # HU-12
    def test_confirmar_llegada(self):
        self.client.post(reverse('confirmar_llegada', args=[self.cita_hoy.pk]))
        self.cita_hoy.refresh_from_db()
        self.assertEqual(self.cita_hoy.estado, Cita.EN_ESPERA)
        self.assertIsNotNone(self.cita_hoy.llegada_en)

    def test_llegada_solo_para_citas_de_hoy(self):
        self.client.post(reverse('confirmar_llegada', args=[self.cita_manana.pk]))
        self.cita_manana.refresh_from_db()
        self.assertEqual(self.cita_manana.estado, Cita.AGENDADA)

    def test_notificacion_al_medico(self):
        self.client.post(reverse('confirmar_llegada', args=[self.cita_hoy.pk]))
        self.client.force_login(self.medico)
        pacientes = self.client.get(reverse('api_en_espera')).json()['pacientes']
        self.assertEqual([p['id'] for p in pacientes], [self.cita_hoy.pk])
        self.client.force_login(self.medico2)
        self.assertEqual(self.client.get(reverse('api_en_espera')).json()['pacientes'], [])

    def test_agenda_del_medico_muestra_boton_atender(self):
        self.client.post(reverse('confirmar_llegada', args=[self.cita_hoy.pk]))
        self.client.force_login(self.medico)
        self.assertContains(self.client.get(reverse('agenda')), reverse('nueva_atencion', args=[self.cita_hoy.pk]))


class InactividadTests(BaseTest):
    """HU-NF06: el polling de notificaciones no mantiene viva la sesión."""

    def test_sesion_expira_aunque_haya_polling(self):
        self.client.force_login(self.medico)
        self.client.get(reverse('dashboard'))
        session = self.client.session
        session['ultima_actividad'] -= 16 * 60
        session.save()
        self.assertEqual(self.client.get(reverse('api_en_espera')).status_code, 401)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
