# Migracion de focus.py a Rust + Slint

## Objetivo
Portar la aplicacion actual de checklist en Python a Rust usando Slint, manteniendo la funcionalidad existente y mejorando el rendimiento de renderizado y redimensionado.

## Inventario funcional actual
- Persistencia JSON en un archivo por usuario:
  - `active`: tareas activas.
  - `history`: tareas completadas, limitado a 250 entradas.
  - `settings`: tema, tabs, always-on-top, accesibilidad y otros ajustes.
- Tareas activas con estos campos:
  - `id`
  - `text`
  - `done`
  - `current`
  - `created_at`
  - `completed_at`
  - `extra_info`
  - `due_date`
  - `tab`
- Operaciones principales sobre tareas:
  - agregar
  - editar
  - eliminar con confirmacion
  - marcar como completada
  - deshacer completado durante 3 segundos
  - restaurar desde historial
  - reordenar por drag and drop
  - marcar una sola tarea como `current`, promocionandola al inicio
- Tabs:
  - vista `All`
  - tabs definidas por el usuario
  - prioridad `high`, `normal`, `low`
  - alta, reordenamiento y eliminacion
  - reasignacion a `General` al eliminar una tab
- Filtros y vistas:
  - vista principal
  - historial
  - panel de herramientas
  - filtrado por tab activa
- Metadatos y productividad:
  - fecha de vencimiento opcional
  - tiempo restante
  - barra de progreso hacia vencimiento
  - `extra_info` opcional
  - contadores de tareas pendientes y completadas hoy/mes/anio
- Ajustes:
  - always-on-top persistente
  - tema predefinido o personalizado
  - escala de fuente
  - modo accesible
  - mostrar/ocultar metadatos
  - cantidad visible de tabs en la tira
- Sistema:
  - importacion/exportacion JSON
  - inicio con el sistema en Windows y Linux

## Tareas
- [x] 1. Analizar `focus.py` y documentar la funcionalidad a conservar.
- [x] 2. Crear el proyecto Rust base con `Cargo.toml`, `src/main.rs` y `ui/app.slint`.
- [x] 3. Definir los modelos Rust para tareas, tabs y settings, con serializacion JSON.
- [x] 4. Implementar la capa de persistencia y carga inicial compatible con el JSON actual.
- [x] 5. Disenar la UI principal en Slint para lista, cabecera, tabs y footer.
- [x] 6. Conectar agregar, editar, completar, deshacer, eliminar y marcar `current`.
- [x] 7. Implementar historial y restauracion de tareas.
- [x] 8. Implementar gestion de tabs, filtrado y reordenamiento.
- [ ] 9. Implementar ajustes de ventana, incluyendo always-on-top multiplataforma.
- [ ] 10. Implementar importacion/exportacion y documentar dependencias en `Cargo.toml`.
- [ ] 11. Probar compilacion, revisar paridad funcional y actualizar `README.md`.

## Criterios de migracion
- Mantener compatibilidad con Windows, macOS y Linux.
- Evitar HTML, webview o soluciones embebidas de navegador.
- Usar Slint con renderizado nativo acelerado por GPU.
- Mantener la persistencia y la semantica de datos actuales siempre que sea razonable.
- Hacer un commit por cada tarea completada.

## Siguiente paso
Tarea 9: implementar ajustes de ventana, incluyendo always-on-top multiplataforma.
