# focus

Checklist desktop nativa en Rust + Slint.

## Estado

La migracion principal desde `focus.py` ya esta operativa. La app actual usa Slint con backend `winit`, render nativo acelerado y persistencia JSON compatible con la estructura de datos existente.

## Funcionalidad disponible

- Ventana nativa con renderizado GPU via Slint.
- Toggle de `always on top` persistido.
- Lista principal separada de `History` y `Tools`.
- Crear, editar, completar, deshacer, eliminar y marcar tarea `current`.
- Historial con restauracion.
- Tabs con filtro `All`.
- Gestion de tabs desde `Tools`.
- Reordenamiento de tareas con `Up` y `Down`.
- Reordenamiento y borrado de tabs.
- Importacion y exportacion JSON por ruta.
- Persistencia de `active`, `history` y `settings`.

## Diferencias respecto a focus.py

Estas partes del script original todavia no estan portadas:

- Hover-first header controls.
- Drag and drop real para reordenar.
- Selector completo de fecha de vencimiento y edicion de `due_date`.
- Tema visual configurable, presets y editor de colores.
- Font scale, accessibility mode y toggle de metadatos.
- Startup on login.
- Links clicables dentro del texto de la tarea.
- Sonidos y animaciones del completado.

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
- [src/storage.rs](/i:/focus/src/storage.rs): persistencia, import/export y rutas.
- [ui/app.slint](/i:/focus/ui/app.slint): interfaz Slint.

## Datos

Windows:

`%APPDATA%\focus\checklist.json`

macOS:

`~/Library/Application Support/focus/checklist.json`

Linux:

`~/.focus/checklist.json`
