# Google Drive Sync Info

Esta guia explica como enlazar `focus` con un `focus-sync.json` guardado en
Google Drive.

## Que necesitas

Necesitas dos datos que vienen de Google:

- `client_id`: el OAuth Client ID de tipo `Desktop app`
- `file_id`: el identificador del archivo `focus-sync.json` en Google Drive

Y un tercer dato local:

- `device_id`: una etiqueta para este equipo, por ejemplo `focus-portatil` o `focus-oficina`

## 1. Crear o localizar `focus-sync.json`

Puedes usar un archivo ya existente o crear uno nuevo en Google Drive.

Lo importante es que escritorio y Android apunten al mismo archivo.

Si todavia no existe, puedes:

1. crear un archivo vacio llamado `focus-sync.json`
2. o subir uno desde el escritorio
3. o dejar que otro cliente lo cree primero

## 2. Sacar el `file_id`

Abre el archivo en Google Drive desde el navegador.

La URL suele tener esta forma:

```text
https://drive.google.com/file/d/FILE_ID/view
```

El `file_id` es la parte entre `/d/` y `/view`.

Ejemplo:

```text
https://drive.google.com/file/d/1AbCdEfGhIJkLmNoPqRsTuVwXyZ/view
```

Aqui el `file_id` es:

```text
1AbCdEfGhIJkLmNoPqRsTuVwXyZ
```

## 3. Crear el `client_id` en Google Cloud

1. Abre Google Cloud Console
2. Crea o reutiliza un proyecto
3. Habilita Google Drive API
4. Configura la pantalla de consentimiento OAuth si te la pide
5. Ve a `APIs y servicios > Credenciales`
6. Crea una credencial `OAuth client ID`
7. Elige tipo `Desktop app`

Google te dara un `client_id` parecido a este:

```text
123456789012-abcdefghi1234567890.apps.googleusercontent.com
```

Ese es el valor que debes pegar en `focus`.

## 4. Elegir el `device_id`

El `device_id` no es una clave de Google.

Es solo el nombre de esta instalacion para que, si tienes varios equipos, sepas cual escribio cada cambio.

Puedes dejar el valor sugerido por defecto, o cambiarlo por algo corto y reconocible.

Ejemplos:

- `focus-oficina`
- `focus-portatil`
- `focus-macbook`

## 5. Configurarlo en focus

En `Tools > External sync`:

1. Selecciona `Google Drive`
2. Pega el `client_id`
3. Pega el `file_id`
4. Comprueba o cambia el `Device id`
5. Pulsa `Save sync config`
6. Pulsa `Sync now`

## 6. Login en Google

Si, en escritorio hace falta autorizar la app una vez.

Cuando pulses `Sync now`, `focus` abrira el navegador para que inicies sesion en
Google y concedas acceso al archivo de Drive.

Despues de eso, `focus` guardara un `refresh_token` local para no pedir permiso
cada vez.

## 7. Que significa `External sync`

`focus` siempre guarda una cache local propia:

- `checklist.json`

Y ademas puede usar una fuente compartida externa:

- `focus-sync.json`

La palabra `external` significa "externa a la cache interna de la app".

Por eso hay dos opciones:

- `Local file`: el `focus-sync.json` vive en una ruta local del disco
- `Google Drive`: el `focus-sync.json` vive en Drive y se accede por `file_id`

## 8. Errores habituales

- `client_id` vacio: falta crear la credencial OAuth de escritorio
- `file_id` incorrecto: copiaste la URL completa en vez del id
- archivo no encontrado: el `file_id` no corresponde a un archivo accesible
- permiso denegado: la cuenta de Google no tiene acceso a ese archivo

## 9. Android

Android no reutiliza automaticamente el login del escritorio.

La idea es que ambos clientes apunten al mismo `focus-sync.json`, pero cada
cliente puede necesitar su propio mecanismo de autorizacion o acceso.

## 10. Recomendacion practica

Haz la primera configuracion con el navegador abierto, porque normalmente
necesitaras consultar:

- la URL del archivo para sacar el `file_id`
- Google Cloud Console para copiar el `client_id`
