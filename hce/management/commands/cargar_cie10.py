"""HU-17: carga masiva del catálogo CIE-10 desde un CSV (columnas: codigo, descripcion).

Uso: python manage.py cargar_cie10 cie10.csv [--delimitador ";"]
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from hce.models import Cie10


class Command(BaseCommand):
    help = 'Importa o actualiza el catálogo CIE-10 desde un archivo CSV'

    def add_arguments(self, parser):
        parser.add_argument('archivo')
        parser.add_argument('--delimitador', default=',')

    def handle(self, archivo, delimitador, **opciones):
        try:
            with open(archivo, encoding='utf-8-sig', newline='') as f:
                filas = list(csv.reader(f, delimiter=delimitador))
        except OSError as error:
            raise CommandError(f'No se pudo leer el archivo: {error}')

        if filas and filas[0] and filas[0][0].strip().lower() in ('codigo', 'código', 'code'):
            filas = filas[1:]
        existentes = {c.codigo: c for c in Cie10.objects.all()}
        nuevos, actualizados = [], []
        for fila in filas:
            if len(fila) < 2 or not fila[0].strip():
                continue
            codigo, descripcion = fila[0].strip().upper(), fila[1].strip()[:255]
            if codigo in existentes:
                if existentes[codigo].descripcion != descripcion:
                    existentes[codigo].descripcion = descripcion
                    actualizados.append(existentes[codigo])
            else:
                existentes[codigo] = Cie10(codigo=codigo, descripcion=descripcion)
                nuevos.append(existentes[codigo])
        Cie10.objects.bulk_create(nuevos, batch_size=1000)
        Cie10.objects.bulk_update(actualizados, ['descripcion'], batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f'CIE-10: {len(nuevos)} nuevos, {len(actualizados)} actualizados.'))
