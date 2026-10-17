#!/usr/bin/env bash
# Build de Render: dependencias, archivos estáticos, migraciones y datos demo opcionales
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

if [ "$CARGAR_DEMO" = "True" ]; then
    python manage.py cargar_demo
fi
