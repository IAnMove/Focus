# focus

Checklist desktop nativa en Rust + Slint.

## Estado

La migracion principal desde `focus.py` ya esta operativa. La app actual usa Slint con backend `winit`, render nativo acelerado y persistencia JSON compatible con la estructura de datos existente.

La paridad de UX/UI ya cubre la mayor parte del flujo diario: lista principal, `History`, `Tools`, presets visuales, accesibilidad, `always on top`, `due_date`, reordenamiento, enlaces y arranque con el sistema.

## Funcionalidad disponible

- Ventana nativa con renderizado GPU via Slint.
- Toggle de `always on top` persistido.
- Lista principal separada de `History` y `Tools`.
- Header con acciones hover estables.
- Crear, editar, completar, deshacer, eliminar y marcar tarea `current`.
- Historial con restauracion.
- Tabs con filtro `All`, overflow lateral y desplazamiento de ventana visible.
- Gestion de tabs desde `Tools`.
- Reordenamiento de tareas con `Up` y `Down` y drag handle.
- Reordenamiento y borrado de tabs.
- Presets `warm`, `forest`, `ocean`, `rose` y `dark`.
- Escala de fuente, modo accesible y toggle de metadata.
- `due_date` editable en el draft usando `YYYY-MM-DD` o `YYYY-MM-DD HH:MM`.
- Tiempo restante, overdue y barra de progreso hacia vencimiento.
- Enlaces detectados dentro de tarea o `extra_info`, abribles desde la tarjeta.
- Sonidos base para add, click y complete.
- Importacion y exportacion JSON por ruta.
- `About` con version, commit y enlace del proyecto.
- Inicio con el sistema en Windows y Linux.
- Sync externo opcional con `focus-sync.json`, merge bidireccional y recarga manual desde `Tools`.
- Seleccion de proveedor de sync: `local_file` o `google_drive`.
- Configuracion inicial de Google Drive en `Tools` con `client_id` y `file_id`.
- OAuth real para Google Drive en escritorio con autorizacion via navegador y `refresh_token` persistido localmente.
- Persistencia de `active`, `history` y `settings`.

## Diferencias respecto a focus.py

Estas partes del script original o del roadmap de sync todavia no estan cerradas:

- Editor de tema personalizado completo.
- Persistencia segura de tokens de Google Drive.

## Sync externo

La app ya soporta una fuente externa opcional `focus-sync.json` y dos modos de
proveedor:

- cache local: `checklist.json`
- proveedor `local_file`: ruta directa a `focus-sync.json`
- proveedor `google_drive`: configuracion local de `client_id` + `file_id`
- accion manual disponible: `Sync now`

Estado actual:

- `local_file` ya hace push proactivo y merge por `updated_at` / `deleted_at`
- `google_drive` ya descarga, mezcla y vuelve a subir `focus-sync.json` usando OAuth de escritorio
- la primera sincronizacion manual abre el navegador para conceder acceso y guardar el `refresh_token`
- la persistencia de tokens sigue siendo local en claro dentro de `checklist.json`; el almacenamiento seguro queda pendiente

## Ejecutar

En desarrollo:

```powershell
cargo run
```

Build release:

```powershell
cargo build --release
```

Compilar sin ejecutar:

```powershell
cargo build
```

Binario resultante:

```powershell
target\release\focus.exe
```

## Instalacion

La app se puede distribuir en Windows, Linux y macOS, pero el binario de cada
plataforma se genera mejor en esa misma plataforma.

### Windows

1. Descargar el ZIP de la release.
2. Descomprimirlo.
3. Ejecutar `focus.exe`.

### Linux

1. Descargar el artefacto de la release.
2. Descomprimirlo.
3. Dar permisos de ejecucion al binario si hace falta:

```bash
chmod +x focus
```

4. Ejecutar `./focus`.

### macOS

1. Descargar el artefacto de la release.
2. Descomprimirlo.
3. Abrir la app o ejecutar el binario generado para macOS.

## Releases

La forma recomendada de publicar una release es subir un asset por plataforma:

- `focus-windows.zip`
- `focus-linux.tar.gz`
- `focus-macos.zip`

Si quieres automatizarlo, lo siguiente natural es un workflow de GitHub Actions
con una matriz por sistema operativo.

## Dependencias

Las dependencias clave estan documentadas en [Cargo.toml](/i:/focus/Cargo.toml):

- `slint`: UI nativa y acceso a `winit`.
- `slint-build`: compilacion de `ui/app.slint`.
- `serde` y `serde_json`: modelos y persistencia JSON.
- `chrono`: timestamps y contadores temporales.

## Estructura

- [src/main.rs](/i:/focus/src/main.rs): estado de la app, callbacks y wiring UI.
- [src/model.rs](/i:/focus/src/model.rs): modelos y normalizacion de datos.
- [src/storage.rs](/i:/focus/src/storage.rs): persistencia, import/export, sync y rutas.
- [src/audio.rs](/i:/focus/src/audio.rs): sonidos base por plataforma.
- [ui/app.slint](/i:/focus/ui/app.slint): interfaz Slint.
- [docs/sync-schema.md](/i:/focus/docs/sync-schema.md): contrato compartido de `focus-sync.json`.
- [docs/google-drive-setup.md](/i:/focus/docs/google-drive-setup.md): configuracion prevista para Google Drive.

## Datos

Windows:

`%APPDATA%\focus\checklist.json`

macOS:

`~/Library/Application Support/focus/checklist.json`

Linux:

`~/.focus/checklist.json`

## Demo

Si quieres enseñar la app sin usar tu configuracion real, usa
[demo/settings.json](/i:/focus/demo/settings.json) como base. Tambien tienes
una copia con el nombre real de la app en
[demo/checklist.demo.json](/i:/focus/demo/checklist.demo.json).
