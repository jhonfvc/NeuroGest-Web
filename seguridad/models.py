from django.db import models
from django.contrib.auth.models import AbstractUser

class Usuario(AbstractUser):
    ROLES = (
        ('ADMIN', 'Administrador'),
        ('RECEPCION', 'Recepcionista'),
        ('MEDICO', 'Médico Neurólogo'),
    )

    rol = models.CharField(max_length=15, choices=ROLES, default='RECEPCION', verbose_name='Rol en el Sistema')
    dni = models.CharField(max_length=8, unique=True, null=True, blank=True, verbose_name='DNI')
    telefono = models.CharField(max_length=15, null=True, blank=True, verbose_name='Teléfono')

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"