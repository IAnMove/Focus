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
- [x] 9. Implementar ajustes de ventana, incluyendo always-on-top multiplataforma.
- [x] 10. Implementar importacion/exportacion y documentar dependencias en `Cargo.toml`.
- [x] 11. Probar compilacion, revisar paridad funcional y actualizar `README.md`.

## Tareas pendientes de paridad con `focus.py`
- [x] 12. Rehacer la cabecera para que muestre acciones de forma estable al entrar en el bloque del titulo y las oculte al salir, sin parpadeo ni perdida de clicks.
- [x] 13. Rehacer las acciones por tarea con iconos compactos siempre visibles a la derecha y paso automatico a una fila inferior al reducir ancho.
- [x] 14. Corregir la interaccion de la fila de tarea para que funcionen `done`, `current`, `edit` y `delete` en todos los modos de ancho.
- [x] 15. Recuperar los presets visuales del script original: `warm`, `forest`, `ocean`, `rose` y `dark`.
- [x] 16. Recuperar ajustes visuales persistentes: escala de fuente, modo accesible y mostrar/ocultar metadata.
- [x] 17. Portar el panel `About` al final de `Tools`, con version, commit y enlace del proyecto.
- [x] 18. Limpiar la cabecera principal quitando el texto de estado tecnico y moviendo la informacion de version solo a `About`.
- [x] 19. Recuperar overflow de tabs con flechas laterales y ventana deslizante de tabs visibles.
- [x] 20. Hacer responsive la tira de tabs para que muestre al menos `All`, `General` y el espacio de navegacion lateral cuando haya overflow.
- [x] 21. Recuperar sonidos equivalentes al script original para add, click y complete, con comportamiento multiplataforma razonable.
- [ ] 22. Portar selector y edicion completa de `due_date`, tiempo restante y progreso con el nivel de detalle del script original.
- [ ] 23. Recuperar drag and drop real para reordenar tareas, manteniendo persistencia correcta.
- [ ] 24. Recuperar inicio con el sistema en Windows y Linux.
- [ ] 25. Recuperar enlaces clicables dentro del texto de la tarea y el comportamiento asociado.
- [ ] 26. Revisar paridad final de UX/UI frente a `focus.py` y actualizar `README.md` con el estado real.

## Tareas de sincronizacion externa
- [x] 27. Definir y documentar el esquema compartido de `focus-sync.json`, con ids estables, timestamps UTC y borrado logico.
- [x] 28. Extender los modelos Rust para soportar el archivo sincronizado y la configuracion local de cache + fuente externa.
- [x] 29. Implementar lectura y escritura de `focus-sync.json` usando el archivo local como cache interna.
- [x] 30. Anadir en `Tools` la configuracion opcional de sync externo y el boton manual `Sync` para descargar/recargar desde la fuente de verdad.
- [ ] 31. Propagar de forma proactiva cada cambio local al archivo de sync cuando la opcion este activada.
- [ ] 32. Implementar merge basico entre cache local y archivo externo con prioridad por `updated_at` y soporte de `deleted_at`.
- [ ] 33. Documentar para Android el contrato de lectura/escritura y las reglas minimas de compatibilidad.

## Criterios de migracion
- Mantener compatibilidad con Windows, macOS y Linux.
- Evitar HTML, webview o soluciones embebidas de navegador.
- Usar Slint con renderizado nativo acelerado por GPU.
- Mantener la persistencia y la semantica de datos actuales siempre que sea razonable.
- Hacer un commit por cada tarea completada.

## Siguiente paso
Tarea 22: portar selector y edicion completa de `due_date`, tiempo restante y progreso con el nivel de detalle del script original.
