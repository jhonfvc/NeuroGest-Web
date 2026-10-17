import re

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .forms import UsuarioCreacionForm
from .models import Usuario

CLAVE = 'ClaveSegura#2026'


def crear_usuario(username, rol=Usuario.RECEPCION, **extra):
    datos = {'email': f'{username}@neurogest.pe', 'rol': rol}
    datos.update(extra)
    return Usuario.objects.create_user(username, password=CLAVE, **datos)


class LoginYDashboardTests(TestCase):
    """HU-01: login y redirección según rol."""

    def test_login_correcto_redirige_al_dashboard(self):
        crear_usuario('recep')
        resp = self.client.post(reverse('login'), {'username': 'recep', 'password': CLAVE})
        self.assertRedirects(resp, reverse('dashboard'))

    def test_login_incorrecto_muestra_error(self):
        crear_usuario('recep')
        resp = self.client.post(reverse('login'), {'username': 'recep', 'password': 'mala'})
        self.assertContains(resp, 'Usuario o contraseña incorrectos.')

    def test_dashboard_por_rol(self):
        casos = [
            (Usuario.RECEPCION, 'seguridad/dashboard_recepcion.html'),
            (Usuario.MEDICO, 'seguridad/dashboard_medico.html'),
            (Usuario.ADMIN, 'seguridad/dashboard_admin.html'),
        ]
        for rol, plantilla in casos:
            with self.subTest(rol=rol):
                self.client.force_login(crear_usuario(f'u_{rol.lower()}', rol=rol))
                self.assertTemplateUsed(self.client.get(reverse('dashboard')), plantilla)

    def test_dashboard_sin_sesion_redirige_al_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_logout_solo_por_post(self):
        self.client.force_login(crear_usuario('recep'))
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))


class SeguridadConfigTests(TestCase):
    """HU-NF06: Bcrypt y expiración de sesión."""

    def test_clave_guardada_con_bcrypt(self):
        usuario = crear_usuario('recep')
        self.assertTrue(usuario.password.startswith('bcrypt_sha256$'))

    def test_sesion_expira_a_los_15_minutos(self):
        self.client.force_login(crear_usuario('recep'))
        self.client.get(reverse('dashboard'))
        self.assertEqual(self.client.session.get_expiry_age(), 15 * 60)


class RecuperarClaveTests(TestCase):
    """HU-02: recuperación de contraseña con token por correo."""

    def test_envia_correo_y_permite_cambiar_clave(self):
        crear_usuario('recep')
        resp = self.client.post(reverse('password_reset'), {'email': 'recep@neurogest.pe'})
        self.assertRedirects(resp, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

        enlace = re.search(r'https?://[^/]+(/recuperar/\S+/)', mail.outbox[0].body).group(1)
        resp = self.client.get(enlace, follow=True)
        nueva = 'OtraClave#2026'
        resp = self.client.post(resp.redirect_chain[-1][0], {'new_password1': nueva, 'new_password2': nueva})
        self.assertRedirects(resp, reverse('password_reset_complete'))
        self.assertTrue(Usuario.objects.get(username='recep').check_password(nueva))

    def test_rechaza_clave_corta(self):
        crear_usuario('recep')
        self.client.post(reverse('password_reset'), {'email': 'recep@neurogest.pe'})
        enlace = re.search(r'https?://[^/]+(/recuperar/\S+/)', mail.outbox[0].body).group(1)
        url = self.client.get(enlace, follow=True).redirect_chain[-1][0]
        resp = self.client.post(url, {'new_password1': 'abc12', 'new_password2': 'abc12'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)

    def test_token_invalido(self):
        resp = self.client.get(reverse('password_reset_confirm', args=['MQ', 'token-falso']))
        self.assertContains(resp, 'no es válido o ya venció')


class CrearUsuarioTests(TestCase):
    """HU-03: alta de usuarios, solo para el administrador."""

    def setUp(self):
        self.admin = crear_usuario('admin', rol=Usuario.ADMIN)
        crear_usuario('existente', dni='12345678')

    def datos(self, **cambios):
        datos = {
            'username': 'nuevo', 'first_name': 'Ana', 'last_name': 'Ríos',
            'email': 'ana@neurogest.pe', 'dni': '87654321', 'telefono': '987654321',
            'rol': Usuario.MEDICO, 'password1': CLAVE, 'password2': CLAVE,
        }
        datos.update(cambios)
        return datos

    def test_admin_crea_usuario(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('crear_usuario'), self.datos())
        self.assertRedirects(resp, reverse('lista_usuarios'))
        self.assertEqual(Usuario.objects.get(username='nuevo').rol, Usuario.MEDICO)

    def test_dni_duplicado(self):
        form = UsuarioCreacionForm(self.datos(dni='12345678'))
        self.assertIn('dni', form.errors)

    def test_dni_debe_tener_8_digitos(self):
        for dni in ('1234567', '123456789', '1234567a'):
            with self.subTest(dni=dni):
                self.assertIn('dni', UsuarioCreacionForm(self.datos(dni=dni)).errors)

    def test_correo_duplicado_sin_importar_mayusculas(self):
        form = UsuarioCreacionForm(self.datos(email='EXISTENTE@neurogest.pe'))
        self.assertIn('email', form.errors)

    def test_no_permite_crear_administradores(self):
        self.assertIn('rol', UsuarioCreacionForm(self.datos(rol=Usuario.ADMIN)).errors)

    def test_recepcion_no_puede_crear_usuarios(self):
        self.client.force_login(crear_usuario('recep'))
        self.assertEqual(self.client.get(reverse('crear_usuario')).status_code, 403)


class RolesTests(TestCase):
    """HU-04: asignación de roles y restricción de vistas."""

    def setUp(self):
        self.admin = crear_usuario('admin', rol=Usuario.ADMIN)
        self.recep = crear_usuario('recep')
        self.medico = crear_usuario('medico', rol=Usuario.MEDICO)

    def test_admin_cambia_rol(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('cambiar_rol', args=[self.recep.pk]), {'rol': Usuario.MEDICO})
        self.recep.refresh_from_db()
        self.assertEqual(self.recep.rol, Usuario.MEDICO)

    def test_middleware_restringe_modulos(self):
        casos = [
            (self.recep, '/hce/', 403),
            (self.recep, '/usuarios/', 403),
            (self.recep, '/reportes/', 403),
            (self.medico, '/admision/', 403),
            (self.medico, '/usuarios/', 403),
            (self.admin, '/usuarios/', 200),
        ]
        for usuario, url, esperado in casos:
            with self.subTest(usuario=usuario.username, url=url):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(url).status_code, esperado)

    def test_middleware_pide_login(self):
        resp = self.client.get('/hce/')
        self.assertRedirects(resp, f"{reverse('login')}?next=/hce/", fetch_redirect_response=False)

    def test_superusuario_es_admin(self):
        su = Usuario.objects.create_superuser('root', 'root@neurogest.pe', CLAVE)
        self.assertEqual(su.rol, Usuario.ADMIN)


class DesactivarCuentaTests(TestCase):
    """HU-05: desactivación por borrado lógico."""

    def setUp(self):
        self.admin = crear_usuario('admin', rol=Usuario.ADMIN)
        self.recep = crear_usuario('recep')

    def test_desactivar_y_reactivar(self):
        self.client.force_login(self.admin)
        url = reverse('cambiar_estado', args=[self.recep.pk])
        self.client.post(url)
        self.recep.refresh_from_db()
        self.assertFalse(self.recep.is_active)
        self.assertTrue(Usuario.objects.filter(pk=self.recep.pk).exists())
        self.client.post(url)
        self.recep.refresh_from_db()
        self.assertTrue(self.recep.is_active)

    def test_usuario_inactivo_no_puede_iniciar_sesion(self):
        self.recep.is_active = False
        self.recep.save()
        resp = self.client.post(reverse('login'), {'username': 'recep', 'password': CLAVE})
        self.assertContains(resp, 'Usuario o contraseña incorrectos.')

    def test_sesion_abierta_se_cierra_al_desactivar(self):
        self.client.force_login(self.recep)
        Usuario.objects.filter(pk=self.recep.pk).update(is_active=False)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_admin_no_se_desactiva_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('cambiar_estado', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
