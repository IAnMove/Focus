# Google Drive Desktop Setup

## Objetivo

Preparar la app de escritorio para usar Google Drive como proveedor de sync del
mismo `focus-sync.json` que comparte con Android.

Esta fase solo cubre configuracion local:

- `provider = "google_drive"`
- `google_drive_client_id`
- `google_drive_file_id`

El transporte OAuth de escritorio todavia no esta implementado en Rust. La app
ya guarda estos datos y muestra mensajes de estado coherentes en `Tools`.

## Credenciales que necesitas

En Google Cloud:

1. Crear o reutilizar un proyecto.
2. Habilitar Google Drive API.
3. Configurar la pantalla de consentimiento OAuth.
4. Crear un OAuth client de tipo `Desktop app`.

Dato importante:

- Google recomienda un cliente OAuth distinto por plataforma.
- Para este repo necesitas un cliente de escritorio para Rust/Windows/macOS/Linux.
- La app Android debe tener su propio cliente Android.

## Campos que usa focus

### `google_drive_client_id`

El `client_id` del cliente OAuth de tipo `Desktop app`.

Ejemplo:

```text
123456789012-abcdefghi1234567890.apps.googleusercontent.com
```

### `google_drive_file_id`

El identificador del archivo compartido en Drive que actuara como fuente de
verdad.

No es la ruta local de Google Drive Desktop. Es el `fileId` real del archivo en
Drive.

## Alcance OAuth previsto

Para una version posterior con transporte real, hay dos caminos razonables:

- `drive.file`: opcion mas contenida si la app crea o abre el archivo con un
  flujo controlado por la propia app.
- `drive`: opcion mas directa si la app necesita leer y actualizar un archivo
  compartido concreto por `file_id`.

Inferencia:

Para el caso de uso actual, donde escritorio y Android quieren apuntar al mismo
archivo compartido por `file_id`, lo mas probable es que la implementacion
inicial necesite `drive`, salvo que anadamos un flujo adicional de seleccion del
archivo por el usuario.

## Flujo previsto para la siguiente tarea

1. Abrir el navegador del sistema con OAuth para `Desktop app`.
2. Recibir un `authorization_code` con redirect local.
3. Intercambiarlo por `access_token` y `refresh_token`.
4. Guardar los tokens en la configuracion local.
5. Descargar el contenido del `file_id`.
6. Hacer merge con la cache local.
7. Subir el `focus-sync.json` resultante al mismo `file_id`.

## Operaciones Drive previstas

- Leer archivo: `files.get`
- Actualizar contenido: `files.update`
- Para archivos pequenos como `focus-sync.json`, `uploadType=multipart` es
  suficiente.

## Referencias oficiales

- OAuth general: <https://developers.google.com/identity/protocols/oauth2>
- OAuth para apps iOS/Desktop: <https://developers.google.com/identity/protocols/oauth2/native-app>
- Crear credenciales: <https://developers.google.com/workspace/guides/create-credentials>
- Picker/Desktop overview: <https://developers.google.com/workspace/drive/picker/guides/overview-desktop>
- Drive `files.get`: <https://developers.google.com/drive/api/reference/rest/v3/files/get>
- Drive `files.update`: <https://developers.google.com/drive/api/reference/rest/v3/files/update>
- Drive uploads: <https://developers.google.com/workspace/drive/api/guides/manage-uploads>
