# Android Sync Contract

## Objetivo

Este documento describe las reglas minimas para que la app Android pueda leer
y escribir `focus-sync.json` sin romper la compatibilidad con la app de
escritorio.

Usa este archivo como contrato operativo. El esquema base esta resumido en
[docs/sync-schema.md](./sync-schema.md).

## Reglas obligatorias

- Leer y escribir JSON UTF-8.
- Ignorar campos desconocidos.
- Mantener `schema_version`.
- Mantener `last_writer`.
- Usar timestamps UTC en formato ISO 8601, por ejemplo
  `2026-04-07T20:41:12Z`.
- No reutilizar IDs.
- No borrar registros fisicamente al sincronizar: usar `deleted_at`.
- Reescribir el archivo completo tras cada sync exitoso.

## Campos que Android debe soportar

### `shared.tabs[]`

- `id`
- `name`
- `priority`
- `order`
- `updated_at`
- `deleted_at`

### `shared.tasks[]`

- `id`
- `text`
- `status`
- `tab_id`
- `current`
- `order`
- `created_at`
- `updated_at`
- `completed_at`
- `deleted_at`
- `extra_info`
- `due_date`

### `shared.preferences`

- `theme_name`
- `custom_palette`
- `font_scale`
- `accessibility_mode`
- `show_item_meta`
- `updated_at`

## Reglas de merge

Android debe aplicar exactamente estas reglas basicas:

1. Cada tab o task se compara por su "version efectiva".
2. La version efectiva es `deleted_at` si existe; si no, `updated_at`.
3. Entre dos versiones del mismo `id`, gana la mas reciente.
4. Si una entidad tiene `deleted_at != null`, se considera borrada aunque siga
   presente en el archivo.
5. Si un registro solo existe en remoto y su version es mas nueva que
   `last_sync_at`, se conserva.
6. Si un registro solo existe en remoto y su version es anterior o igual a
   `last_sync_at`, puede interpretarse como borrado local y convertirse en
   tombstone con `deleted_at = now`.

## Reglas de escritura

Al modificar datos locales:

- Crear nuevas tasks con `id` estable.
- Actualizar `updated_at` de la entidad modificada.
- Al completar una task:
  - `status = "completed"`
  - `completed_at = now`
  - `updated_at = now`
- Al restaurar una task:
  - `status = "active"`
  - `completed_at = null`
  - `updated_at = now`
- Al borrar una task o tab:
  - no eliminarla del sync payload anterior sin mas
  - marcar `deleted_at = now`
  - en tasks, usar `status = "deleted"`

## Reglas de lectura

Al cargar desde `focus-sync.json`:

- Ignorar tabs con `deleted_at != null`.
- Ignorar tasks con `deleted_at != null`.
- Mapear `status = "active"` a lista activa.
- Mapear `status = "completed"` a historial.
- Si una task referencia una tab ausente o borrada, reasignarla a `General`.
- Si hay varias tasks activas con `current = true`, conservar solo la mas
  reciente por `updated_at`.

## Flujo recomendado en Android

### Arranque

1. Cargar cache local.
2. Si sync externo esta activado, cargar `focus-sync.json`.
3. Hacer merge con `last_sync_at`.
4. Actualizar memoria y cache local.
5. Si el merge produce cambios, reescribir `focus-sync.json`.

### Cambio local

1. Aplicar cambio a memoria.
2. Actualizar `updated_at` del registro afectado.
3. Guardar cache local.
4. Si sync externo esta activado:
   - cargar `focus-sync.json`
   - hacer merge
   - guardar `focus-sync.json`
   - actualizar `last_sync_at`

### Sync manual

1. Cargar cache local.
2. Cargar `focus-sync.json`.
3. Hacer merge bidireccional.
4. Guardar ambos resultados:
   - cache local
   - `focus-sync.json`

## Cosas que Android no debe sincronizar

- `always_on_top`
- startup on login
- posicion o tamano de ventana
- opciones exclusivas de desktop

## Recomendaciones practicas

- Generar un `device_id` estable por instalacion.
- Escribir primero a un archivo temporal y luego renombrar, si la plataforma lo
  permite.
- No asumir que el orden del array coincide con el orden visual final; usar
  `order`.
- No asumir que `updated_at` esta en hora local.

## Encontrar el archivo en Android

Si Android crea `focus-sync.json` en almacenamiento privado, el usuario no
siempre podra verlo desde un gestor de archivos. En Android moderno hay tres
escenarios habituales:

- Almacenamiento interno privado: `Context.filesDir/focus-sync.json`
- Almacenamiento externo privado: `Android/data/<package>/files/focus-sync.json`
- Carpeta visible para el usuario: `Android/media/<package>/focus-sync.json`

Recomendacion operativa:

- Si el usuario debe localizar el archivo manualmente, es mejor escribirlo en
  `Android/media/<package>/focus-sync.json` o exponer un flujo de exportacion
  con el selector del sistema.
- `Android/data/...` suele estar oculto o muy restringido en Android 11+.
- Si el archivo queda en almacenamiento interno privado, el usuario normal no
  podra navegar hasta el sin ADB o sin una opcion de exportar desde la app.

Comandos utiles con ADB:

```bash
adb shell run-as <package> ls files
adb shell run-as <package> cat files/focus-sync.json
adb shell "run-as <package> cat files/focus-sync.json" > focus-sync.json
```

Si la app usa `Android/data/<package>/files`, tambien puede inspeccionarse con:

```bash
adb shell ls /sdcard/Android/data/<package>/files
adb shell cat /sdcard/Android/data/<package>/files/focus-sync.json
```
