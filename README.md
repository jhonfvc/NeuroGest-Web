# NeuroGest-Web — Producto Mínimo Viable (MVP)
Sistema Web de Historias Clínicas y Agendamiento para un consultorio neurológico en Villa El Salvador.
Proyecto de Ingeniería de Software – Grupo 3, UNTELS (2026).

> **Versión MVP – Sprint 2 (Avance 1).** Incluye las 12 historias de usuario del Sprint 2
> (HU-01 a HU-12): seguridad por roles, admisión de pacientes con API de DNI y agendamiento de citas.
> Los módulos de Historias Clínicas (Sprint 3) y Reportes (Sprint 4) están en la rama `main` (versión 1.0).

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
| E03 Historias Clínicas | `hce` | HU-13 a HU-18 (Sprint 3) |
| E04 Reportes | `reportes` | HU-19 y HU-20 (Sprint 4) |

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
