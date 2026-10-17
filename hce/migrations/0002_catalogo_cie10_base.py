from django.db import migrations

from hce.cie10_base import CIE10_BASE


def cargar(apps, schema_editor):
    Cie10 = apps.get_model('hce', 'Cie10')
    existentes = set(Cie10.objects.values_list('codigo', flat=True))
    Cie10.objects.bulk_create([Cie10(codigo=c, descripcion=d) for c, d in CIE10_BASE if c not in existentes])


class Migration(migrations.Migration):

    dependencies = [
        ('hce', '0001_historia_clinica'),
    ]

    operations = [
        migrations.RunPython(cargar, migrations.RunPython.noop),
    ]
