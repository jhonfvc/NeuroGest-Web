"""HU-06: cliente de la API REST de consulta de DNI (RENIEC).

Estrategia de resiliencia (ASR-02 / HU-NF05): presupuesto total de 3 segundos que
incluye hasta 2 reintentos con exponential backoff. Si no hay respuesta válida
dentro de ese tiempo se lanza ReniecNoDisponible y la vista activa el registro manual (HU-07).
"""
import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIEMPO_TOTAL = 3.0
REINTENTOS = 2
BACKOFF_BASE = 0.25


class ReniecNoDisponible(Exception):
    """La API no respondió a tiempo, falló o no está configurada."""


class DniNoEncontrado(Exception):
    """La API respondió, pero el DNI no existe."""


@dataclass
class DatosDni:
    dni: str
    nombres: str
    apellido_paterno: str
    apellido_materno: str
    fecha_nacimiento: str = ''

    def como_dict(self):
        return self.__dict__.copy()


def _primero(datos, *claves):
    for clave in claves:
        valor = datos.get(clave)
        if valor:
            return str(valor).strip()
    return ''


def _interpretar(dni, datos):
    # Acepta los formatos de los proveedores más usados (apis.net.pe / decolecta)
    nombres = _primero(datos, 'nombres', 'first_name', 'nombre')
    paterno = _primero(datos, 'apellidoPaterno', 'apellido_paterno', 'first_last_name')
    materno = _primero(datos, 'apellidoMaterno', 'apellido_materno', 'second_last_name')
    if not (nombres and paterno):
        raise DniNoEncontrado(dni)
    nacimiento = _primero(datos, 'fechaNacimiento', 'fecha_nacimiento', 'birth_date')
    return DatosDni(dni, nombres.title(), paterno.title(), materno.title(), nacimiento)


def consultar_dni(dni):
    url = getattr(settings, 'RENIEC_API_URL', '')
    token = getattr(settings, 'RENIEC_API_TOKEN', '')
    if not (url and token):
        raise ReniecNoDisponible('API de DNI no configurada')

    limite = time.monotonic() + TIEMPO_TOTAL
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    ultimo_error = None

    for intento in range(REINTENTOS + 1):
        restante = limite - time.monotonic()
        if restante <= 0:
            break
        try:
            resp = requests.get(url, params={'numero': dni}, headers=headers, timeout=restante)
            if resp.status_code == 404:
                raise DniNoEncontrado(dni)
            resp.raise_for_status()
            return _interpretar(dni, resp.json())
        except DniNoEncontrado:
            raise
        except (requests.RequestException, ValueError) as error:
            ultimo_error = error
            logger.warning('Consulta DNI falló (intento %s): %s', intento + 1, error)

        espera = BACKOFF_BASE * (2 ** intento)
        if time.monotonic() + espera >= limite:
            break
        time.sleep(espera)

    raise ReniecNoDisponible(str(ultimo_error or 'tiempo de espera agotado'))
