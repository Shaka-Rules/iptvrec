# IPTVrec Dashboard

Panel de control web para IPTVrec. Permite monitorizar, programar y gestionar grabaciones desde el navegador.

## Requisitos

- Python 3.10+
- IPTVrec instalado en `../src/` (relativo a `dashboard/`)
- `tzdata` (necesario en Windows para zona horaria)
- Dependencias: `pip install -r requirements.txt`

## Arranque

```bash
python dashboard/run.py
# Servidor en http://0.0.0.0:3000
```

O directamente con uvicorn desde la raíz del proyecto:

```bash
PYTHONPATH=src python -m uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 3000
```

## Estructura

```
dashboard/
├── run.py                          # Entry point (anade PYTHONPATH y arranca)
├── start.sh                        # Para Linux/systemd
├── requirements.txt                # fastapi, uvicorn, pydantic-settings, pyyaml, python-multipart, tzdata
├── systemd/
│   └── iptvrec-dashboard.service   # Unidad systemd para produccion
├── backend/
│   ├── main.py                     # App FastAPI, middleware CORS, rutas, exception handler
│   ├── config.py                   # Settings (host, port, youtube OAuth, etc.)
│   ├── templates.py                # Helper para servir HTML estaticos
│   ├── api/
│   │   ├── channels.py             # GET /api/channels/{source} - listar/buscar canales con paginacion
│   │   ├── status.py               # GET /api/status - estado completo (activas, recientes, disco, youtube)
│   │   │                           # GET /api/status/validate - validar configuracion
│   │   ├── recordings.py           # GET /api/recordings - lista grabaciones recientes
│   │   │                           # GET /api/recordings/{id}/log - leer log de grabacion
│   │   │                           # POST /api/recordings/{id}/stop - detener grabacion
│   │   │                           # GET /api/recordings/logs - listar logs disponibles
│   │   ├── schedule.py             # GET /api/schedule - listar programacion
│   │   │                           # POST /api/schedule - crear entrada
│   │   │                           # PUT /api/schedule/{id} - actualizar entrada
│   │   │                           # DELETE /api/schedule/{id} - eliminar entrada
│   │   │                           # POST /api/schedule/{id}/enable - toggle habilitar
│   │   ├── wizard.py               # GET /api/wizard/sources - fuentes disponibles
│   │   │                           # GET /api/wizard/channels?source=... - canales de una fuente
│   │   │                           # POST /api/wizard/preview-url - testear URL de stream
│   │   │                           # POST /api/wizard/validate-datetime - validar fecha/hora
│   │   │                           # POST /api/wizard/submit - crear grabacion o programar
│   │   ├── config_api.py           # GET /api/config - leer configuracion YAML
│   │   │                           # POST /api/config - guardar cambios en config
│   │   ├── youtube.py              # GET /auth/youtube/status - estado del token
│   │   │                           # GET /auth/youtube/start - iniciar OAuth
│   │   │                           # GET /auth/youtube/callback - callback OAuth
│   │   └── daemon.py               # GET /api/daemon/status - estado del demonio
│   │                               # POST /api/daemon/start /stop /restart
│   ├── services/
│   │   └── iptvrec.py              # Wrapper a los modulos internos de iptvrec
│   ├── websocket/
│   │   └── logs.py                 # WebSocket /ws/logs/{job_id} y /ws/logs/daemon
│   └── models/
│       └── __init__.py             # Pydantic models (ChannelModel, RecordingModel, etc.)
└── frontend/
    └── templates/                  # 5 paginas HTML con Alpine.js (sin Tailwind CDN)
        ├── index.html              # Dashboard: estado, activas, proximas, recientes, disco, youtube
        ├── recordings.html         # Lista de grabaciones + modal de log con WebSocket
        ├── schedule.html           # Tabla de programacion con CRUD inline
        ├── wizard.html             # Wizard 5 pasos: fuente -> canal -> cuando -> opciones -> confirmar
        └── settings.html           # Ajustes con pestanas: General, Demonio, YouTube, Telegram, Sistema
```

## Paginas

### Dashboard (`/`)
- 4 tarjetas superiores: estado del demonio, grabaciones activas, proximas, espacio en disco
- Lista de grabaciones activas con barra de progreso y boton de detener
- Proximas grabaciones (de la programacion)
- Ultimas grabaciones realizadas
- Widget de espacio en disco (temp + salida)
- Widget de estado de YouTube
- Refresco automatico cada 15 segundos

### Grabaciones (`/recordings`)
- Tabla de grabaciones recientes con estado, tamaño, duracion
- Enlace a YouTube si se subio
- Modal de log en vivo via WebSocket
- Paginacion

### Programacion (`/schedule`)
- Tabla de entradas programadas
- Toggle para habilitar/deshabilitar cada entrada
- Botones de editar y eliminar
- Tooltip con resumen de recurrencia

### Nueva Grabacion (`/wizard`)
5 pasos:
1. **Fuente**: seleccionar entre fuentes configuradas (atresplayer, rtveplay, xtream, m3u)
2. **Canal**: buscar con paginacion y seleccion
3. **Cuando**: tipo (una vez/diario/semanal), fecha, hora, duracion, validacion de conflictos
4. **Opciones**: nombre, formato, YouTube, Telegram
5. **Confirmar**: resumen y botones "Programar" o "Grabar AHORA"

### Ajustes (`/settings`)
Pestanas:
- **General**: directorios, formato, zona horaria, scheduler
- **Demonio**: iniciar/detener/reiniciar, log en vivo
- **YouTube**: estado del token, autenticacion OAuth
- **Telegram**: estado, prueba de envio
- **Sistema**: ffmpeg/ffprobe, validacion de configuracion

## API

Todas las rutas devuelven JSON. CORS abierto para acceso LAN.

### WebSocket
- `ws://host:3000/ws/logs/{job_id}` - log de una grabacion especifica
- `ws://host:3000/ws/logs/daemon` - log del demonio

Mensajes del servidor:
```json
{"type": "ready", "path": "/ruta/al/log"}
{"type": "line", "data": "2026-01-01 ... INFO - mensaje"}
{"type": "error", "message": "Archivo no encontrado"}
```

## Timezone

Todas las fechas se muestran en la zona horaria configurada en `config.yaml` (campo `timezone`). Nunca se muestra UTC al usuario. Las conversiones UTC son solo internas para el scheduler.

## Produccion

### systemd
```bash
sudo cp dashboard/systemd/iptvrec-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now iptvrec-dashboard
```

### Manual
```bash
cd /opt/iptvrec
python dashboard/run.py
# O con nohup / screen / tmux
```
