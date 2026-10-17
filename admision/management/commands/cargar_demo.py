"""Carga usuarios y pacientes ficticios para probar o presentar el sistema en local.

Uso: python manage.py cargar_demo
La contraseña de los usuarios demo se toma de DEMO_PASSWORD (ver .env.example).
"""
import os
from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from admision.models import Cita, Paciente
from seguridad.models import Usuario

USUARIOS = [
    ('admin', 'Admin', 'Sistema', Usuario.ADMIN, '40000001'),
    ('recepcion', 'Carla', 'Ramos', Usuario.RECEPCION, '40000002'),
    ('dr.salazar', 'Miguel', 'Salazar', Usuario.MEDICO, '40000003'),
    ('dra.paredes', 'Lucía', 'Paredes', Usuario.MEDICO, '40000004'),
]

PACIENTES = [
    ('10000001', 'Ana', 'Torres', 'Vega', '1985-03-12', 'F'),
    ('10000002', 'Jorge', 'Huamán', 'Ríos', '1972-11-02', 'M'),
    ('10000003', 'Elena', 'Cárdenas', 'Soto', '1990-07-25', 'F'),
    ('10000004', 'Raúl', 'Mendoza', 'Lara', '1965-01-30', 'M'),
    ('10000005', 'Sofía', 'Navarro', 'Peña', '2001-09-14', 'F'),
]


class Command(BaseCommand):
    help = 'Crea usuarios, pacientes y citas ficticias para la demostración'

    def handle(self, *args, **opciones):
        clave = os.environ.get('DEMO_PASSWORD', 'NeuroGest#Demo2026')
        for username, nombre, apellido, rol, dni in USUARIOS:
            u, creado = Usuario.objects.get_or_create(username=username, defaults={
                'first_name': nombre, 'last_name': apellido, 'rol': rol, 'dni': dni,
                'email': f'{username}@neurogest.demo', 'is_staff': rol == Usuario.ADMIN,
                'is_superuser': rol == Usuario.ADMIN,
            })
            if creado:
                u.set_password(clave)
                u.save()
            self.stdout.write(f"{'Creado' if creado else 'Ya existe'}: {username} ({u.get_rol_display()})")

        for dni, nombres, paterno, materno, nacimiento, sexo in PACIENTES:
            Paciente.objects.get_or_create(dni=dni, defaults={
                'nombres': nombres, 'apellido_paterno': paterno, 'apellido_materno': materno,
                'fecha_nacimiento': nacimiento, 'sexo': sexo, 'telefono': '900000000',
            })

        medicos = list(Usuario.objects.filter(rol=Usuario.MEDICO).order_by('username'))
        hoy = timezone.localdate()
        if medicos and not Cita.objects.exists():
            pacientes = list(Paciente.objects.order_by('dni'))
            agenda = [(0, time(9, 0)), (0, time(10, 0)), (0, time(11, 30)), (1, time(9, 30)), (2, time(16, 0))]
            for i, (dias, hora) in enumerate(agenda):
                Cita.objects.create(paciente=pacientes[i % len(pacientes)], medico=medicos[i % len(medicos)],
                                    fecha=hoy + timedelta(days=dias), hora=hora, motivo='Control neurológico')

        self.stdout.write(self.style.SUCCESS(f'Datos demo listos. Contraseña de los usuarios demo: variable DEMO_PASSWORD '
                                             f'(por defecto la indicada en .env.example).'))
