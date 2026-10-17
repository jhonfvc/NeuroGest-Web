# NeuroGest-Web
Sistema Web de Historias Clínicas y Agendamiento para un consultorio neurológico en Villa El Salvador.
Proyecto de Ingeniería de Software – Grupo 3, UNTELS (2026).

**Stack:** Django 6.1 (patrón MVT) · Tailwind CSS · SQLite en desarrollo (SQL Server en producción) · API REST de DNI.

## Instalación local
```bash
git clone https://github.com/jhonfvc/NeuroGest-Web.git
cd NeuroGest-Web
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # Linux/Mac: cp .env.example .env
python manage.py migrate
python manage.py cargar_demo     # usuarios, pacientes y citas ficticias (opcional)
python manage.py runserver
```
Abrir http://127.0.0.1:8000.

`cargar_demo` crea los usuarios `admin`, `recepcion`, `dr.salazar` y `dra.paredes` con la contraseña definida en `DEMO_PASSWORD` del `.env`.

Sin `RENIEC_API_TOKEN` el sistema funciona igual: la búsqueda por DNI pasa automáticamente al registro manual (HU-07).

## Pruebas
```bash
python manage.py test
```

## Módulos y Historias de Usuario
| Épica | App | HU |
|---|---|---|
| E01 Seguridad | `seguridad` | HU-01 Login por roles · HU-02 Recuperación de clave · HU-03 Creación de usuarios · HU-04 Roles (RBAC) · HU-05 Desactivación de cuenta |
| E02 Admisión y Citas | `admision` | HU-06 Búsqueda por DNI (API) · HU-07 Registro manual · HU-08 Agendamiento · HU-09 Agenda diaria · HU-10 Reprogramación · HU-11 Cancelación · HU-12 Recepción del paciente |
| E03 Historias Clínicas | `hce` | HU-13 Búsqueda de expediente · HU-14 Historial cronológico · HU-15 Triaje e IMC · HU-16 Evolución médica · HU-17 Diagnóstico CIE-10 · HU-18 Prescripción médica |
| E04 Reportes | `reportes` | HU-19 Receta en PDF · HU-20 Reporte de atenciones (gráfico, Excel y PDF) |

### Catálogo CIE-10
La migración carga un catálogo base de diagnósticos neurológicos frecuentes. Para importar el catálogo completo:
```bash
python manage.py cargar_cie10 cie10.csv            # columnas: codigo,descripcion
python manage.py cargar_cie10 cie10.csv --delimitador ";"
```

### Datos del consultorio (membrete de la receta)
Se configuran con `CONSULTORIO_NOMBRE`, `CONSULTORIO_DIRECCION` y `CONSULTORIO_TELEFONO` en el `.env`.

### Permisos por rol (HU-04)
| Ruta | Administrador | Recepción | Médico |
|---|---|---|---|
| `/usuarios/` | ✔ | – | – |
| `/admision/` (pacientes) | ✔ | ✔ | – |
| `/citas/agenda/`, `/citas/calendario/` | ✔ | ✔ | ✔ (solo sus citas) |
| `/hce/` | ✔ | – | ✔ |
| `/reportes/` | ✔ | – | – |

## Flujo de trabajo (GitFlow)
- `main`: versión estable entregada · `develop`: integración del Sprint · `feature/*`: una rama por módulo/HU.
- Commits con el formato `[HU-XX] Descripción`.
- Todo cambio entra a `develop` mediante Pull Request.
- Nunca subir `venv/`, `db.sqlite3` ni `.env`.
