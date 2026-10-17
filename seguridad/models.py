from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import RegexValidator
from django.db import models

validar_dni = RegexValidator(r'^\d{8}$', 'El DNI debe tener exactamente 8 dígitos.')


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # El superusuario siempre entra como Administrador
        extra_fields.setdefault('rol', Usuario.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class Usuario(AbstractUser):
    ADMIN = 'ADMIN'
    RECEPCION = 'RECEPCION'
    MEDICO = 'MEDICO'

    ROLES = (
        (ADMIN, 'Administrador'),
        (RECEPCION, 'Recepcionista'),
        (MEDICO, 'Médico Neurólogo'),
    )

    rol = models.CharField(max_length=15, choices=ROLES, default=RECEPCION, verbose_name='Rol en el Sistema')
    dni = models.CharField(max_length=8, unique=True, null=True, blank=True, validators=[validar_dni], verbose_name='DNI')
    telefono = models.CharField(max_length=15, null=True, blank=True, verbose_name='Teléfono')
    # HU-03: el correo es obligatorio y único (se usa en la recuperación de clave)
    email = models.EmailField(unique=True, verbose_name='Correo electrónico')

    REQUIRED_FIELDS = ['email']

    objects = UsuarioManager()

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"

    @property
    def es_admin(self):
        return self.is_superuser or self.rol == self.ADMIN
