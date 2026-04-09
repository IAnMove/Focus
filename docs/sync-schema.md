# Sync Schema

## Objetivo

`focus-sync.json` es el archivo compartido entre escritorio y Android.
Debe poder leerse y escribirse desde ambas apps sin depender del formato local
de cache (`checklist.json`).

La app de escritorio seguira usando un archivo local como cache interna. Si el
sync externo esta activado, cada cambio local se propagara al archivo externo y
el boton `Sync` forzara una recarga desde ese archivo.

## Reglas generales

- Formato: JSON UTF-8.
- Versionado: campo `schema_version`.
- Fechas: ISO 8601 en UTC, por ejemplo `2026-04-07T20:41:12Z`.
- IDs: `string`, no enteros. Recomendado `uuid` o `ulid`.
- Borrados: logicos mediante `deleted_at`, no eliminacion inmediata.
- Compatibilidad: ambas apps deben ignorar campos desconocidos.
- Plataforma: `always_on_top`, startup, posicion de ventana y otros ajustes
  locales no se sincronizan.

## Estructura

```json
{
  "schema_version": 1,
  "updated_at": "2026-04-07T20:41:12Z",
  "last_writer": {
    "device_id": "desktop-win11-ina",
    "app_id": "focus-desktop",
    "app_version": "0.1.0"
  },
  "shared": {
    "tabs": [
      {
        "id": "general",
        "name": "General",
        "priority": "normal",
        "order": 0,
        "updated_at": "2026-04-07T20:41:12Z",
        "deleted_at": null
      }
    ],
    "tasks": [
      {
        "id": "tsk_01JQ2J18ENYQF7VMS96Q6C3F0W",
        "text": "Finish what is already in progress",
        "status": "active",
        "tab_id": "general",
        "current": true,
        "order": 0,
        "created_at": "2026-04-07T20:10:00Z",
        "updated_at": "2026-04-07T20:41:12Z",
        "completed_at": null,
        "deleted_at": null,
        "extra_info": "",
        "due_date": null
      }
    ],
    "preferences": {
      "theme_name": "warm",
      "custom_palette": {},
      "font_scale": 1.0,
      "accessibility_mode": false,
      "show_item_meta": true,
      "updated_at": "2026-04-07T20:41:12Z"
    }
  }
}
```

## Tabs

- `id`: identificador estable compartido.
- `name`: nombre visible.
- `priority`: `high`, `normal`, `low`.
- `order`: orden visual.
- `updated_at`: ultima mutacion.
- `deleted_at`: `null` si existe, timestamp UTC si fue eliminada.

La tab `General` debe existir siempre. Se recomienda `id: "general"`.

## Tasks

- `id`: identificador estable compartido.
- `text`: texto principal.
- `status`: `active`, `completed` o `deleted`.
- `tab_id`: referencia a `shared.tabs[].id`.
- `current`: indica la tarea destacada actual.
- `order`: orden visual entre tareas activas.
- `created_at`: alta inicial.
- `updated_at`: ultima mutacion.
- `completed_at`: timestamp UTC o `null`.
- `deleted_at`: timestamp UTC o `null`.
- `extra_info`: texto opcional.
- `due_date`: timestamp UTC o `null`.

## Preferences compartidas

Se sincronizan solo los ajustes que deben verse igual en ambos clientes:

- `theme_name`
- `custom_palette`
- `font_scale`
- `accessibility_mode`
- `show_item_meta`
- `updated_at`

No se sincronizan:

- `always_on_top`
- `tab_visible_count`
- startup on login
- posicion y tamano de ventana
- cualquier ajuste especifico de plataforma

## Reglas de merge

Version minima:

- Cada tab o task se compara por una "version efectiva".
- La version efectiva es `deleted_at` si existe; si no, `updated_at`.
- Gana la version mas reciente.
- Si `deleted_at` no es `null`, la entidad se considera borrada aunque siga
  presente en el archivo.
- Si una tarea apunta a una tab borrada, debe reasignarse a `General`.
- Solo una tarea activa deberia quedar con `current = true`; si hay varias,
  gana la de `updated_at` mas reciente.
- `shared.preferences` se compara por `preferences.updated_at`.
- Si un registro remoto falta en local pero su version remota es anterior o
  igual a `last_sync_at`, puede convertirse en tombstone local al hacer merge.

## Relacion con la cache local

- `checklist.json`: cache local e interna de la app.
- `focus-sync.json`: fuente de verdad opcional compartida entre dispositivos.

Si el sync externo esta activado:

1. La app carga el archivo externo.
2. Convierte o mezcla contra la cache local.
3. Actualiza la UI.
4. Tras cada accion del usuario, escribe cache local y archivo externo.

El boton `Sync` debe forzar una recarga desde el archivo externo.

## Referencia para Android

La guia operativa para la app Android esta en
[docs/android-sync.md](./android-sync.md).

## Compatibilidad con el formato actual

El archivo local actual separa:

- `active`
- `history`
- `settings`

El archivo de sync compartido no debe depender de esa separacion. En su lugar
usa:

- `shared.tasks` con `status`
- `shared.tabs`
- `shared.preferences`

Esto hace el contrato mas estable para Android y escritorio.
