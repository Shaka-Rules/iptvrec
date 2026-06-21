# iptvrec — Sistema de grabación IPTV

Graba canales de **atresplayer**, **rtveplay**, **Xtream Codes** y **playlists M3U8** en un
contenedor LXC Debian. Portátil (copiar + descomprimir + `install.sh`), resiliente
a cortes del stream, con programador propio, copia final verificada por sha256,
notificaciones por Telegram y subida opcional a YouTube.

## Requisitos
- Debian 13 (o similar) con `python3` (≥3.11) y `python3-venv`.
- `ffmpeg` y `ffprobe`: `apt-get install -y ffmpeg`.

## Instalación
```bash
cp iptvrec.tar.gz /home/shaka/
cd /home/shaka && tar xzf iptvrec.tar.gz && cd iptvrec
./install.sh
./bin/iptvrec validate
```
`install.sh` crea un `.venv` **dentro** de la carpeta e instala las dependencias;
no toca el sistema. Todo es relativo a la carpeta: funciona la copies donde la copies.

> Si algún `.sh` falla con errores de `\r` (finales de línea Windows), normaliza:
> `sed -i 's/\r$//' install.sh start.sh stop.sh bin/iptvrec`

## Configuración
- `config/config.yaml` — opciones globales (rutas, formato, Telegram, YouTube,
  Xtream, rtveplay, zona horaria…). **Cada opción está documentada** en
  `config/config.example.yaml`.
- `config/schedule.yaml` — grabaciones programadas (ejemplos en
  `config/schedule.example.yaml`).

Rutas configurables: `output_dir` (final) y `temp_dir` (temporal). Formato de
salida `output_format` (`mp4` por defecto, también `mkv`/`ts`).

## Descubrir canales
```bash
./bin/iptvrec channels atresplayer            # nombre | slug | id
./bin/iptvrec channels atresplayer --verify   # además resuelve el id real
./bin/iptvrec channels rtveplay               # nombre | slug
./bin/iptvrec channels xtream                 # stream_id | nombre | categoría
./bin/iptvrec channels m3u8 --playlist lista.m3u
```
En el programador puedes referir el canal por **nombre**, por slug/id
(atresplayer, rtveplay) o por stream_id (xtream).

## Programar grabaciones
Edita `config/schedule.yaml` (se relee en caliente) o usa la CLI:
```bash
./bin/iptvrec schedule add --id telediario --name "Telediario" \
    --source xtream --channel "La 1 HD" --type daily --time 15:00 --duration 3600
./bin/iptvrec schedule list
./bin/iptvrec schedule disable --id telediario
```
La hora de fin = inicio + `duration` (segundos), con cambio de día automático.
Recurrencia: `once` (fecha+hora), `daily` (hora) o `weekly` (días + hora).

## Arrancar / parar el programador
```bash
./start.sh                       # demonio en segundo plano
./bin/iptvrec status             # estado general
./bin/iptvrec status --watch 2   # refresco continuo
./stop.sh                        # parada limpia (lo grabado se ensambla y copia)
```

## Grabación inmediata (ad-hoc)
```bash
./bin/iptvrec record --source atresplayer --channel lasexta --duration 120
./bin/iptvrec record --source rtveplay --channel "La 1" --duration 3600
./bin/iptvrec record --source xtream --channel "DAZN 1" --duration 5400 --detach
```

## Telegram
Activa `telegram.enabled: true` con tu `bot_token`/`chat_id` en `config.yaml` y prueba:
```bash
./bin/iptvrec test-telegram
```
Avisa al **iniciar**, **terminar** o **fallar** una grabación, y de la **caducidad
del token de YouTube**.

## YouTube (subida automática)
1. `config/credentials.json` ya está (cliente OAuth de escritorio).
2. Autoriza una vez, desde el LXC headless, con un túnel SSH desde tu equipo:
   ```bash
   # en TU equipo (deja la sesión abierta):
   ssh -L 8080:localhost:8080 usuario@<host-del-lxc>
   # en el LXC:
   ./bin/iptvrec youtube-auth
   ```
   Abre en tu navegador la URL que imprime; el redirect a `localhost:8080` llega
   al LXC por el túnel y se guarda `config/token.json`.
3. En cada grabación con `youtube: { upload: true }` se sube tras la copia
   verificada (privado por defecto). El token **se renueva solo**; si fuera a
   caducar (modo *Testing* de Google = 7 días), recibes aviso por Telegram para
   re-ejecutar `youtube-auth`. Para tokens duraderos, publica la app en Google
   Cloud y pon `youtube.token_lifetime_days: 0`.

## Seguridad
`config.yaml`, `credentials.json` y `token.json` contienen secretos y están en
`.gitignore`. Si vas a compartir el código, **rota** el token de Telegram (BotFather)
y regenera el `client_secret` de Google.

## Estructura
- `src/iptvrec/` — código: `providers/` (atresplayer, rtveplay, xtream, m3u8),
  `recorder.py`, `scheduler.py`, `verify_copy.py`, `youtube.py`, `notify.py`,
  `monitor.py`, `cli.py`.
- `config/` — configuración · `logs/` — registros · `recordings/` — salida ·
  `tmp/` — temporal · `state/` — estado en ejecución.
