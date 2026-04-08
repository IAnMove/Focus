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
- Sync externo opcional con `focus-sync.json` y recarga manual desde `Tools`.
- Persistencia de `active`, `history` y `settings`.

## Diferencias respecto a focus.py

Estas partes del script original o del roadmap de sync todavia no estan cerradas:

- Editor de tema personalizado completo.
- Sync proactivo al archivo externo despues de cada cambio local.
- Merge entre cache local y archivo externo por `updated_at` / `deleted_at`.
- Documentacion especifica del contrato Android para sync bidireccional.

## Sync externo

La app ya soporta una fuente externa opcional `focus-sync.json`:

- cache local: `checklist.json`
- fuente compartida opcional: `focus-sync.json`
- accion manual disponible: `Sync now`

Pendiente:

- subida proactiva de cambios locales
- merge automatico entre cache y fuente externa

## Ejecutar

En desarrollo:

```powershell
cargo run
```

Build release:

```powershell
cargo run --release
```

Compilar sin ejecutar:

```powershell
cargo build
```

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

## Datos

Windows:

`%APPDATA%\focus\checklist.json`

macOS:

`~/Library/Application Support/focus/checklist.json`

Linux:

`~/.focus/checklist.json`
