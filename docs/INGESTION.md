# Importación de evidencias (fase 2)

## Uso

Crear o abrir un caso, seleccionar **Abrir caso**, cargar un archivo y esperar su validación. Elegir las hojas e inspeccionar la muestra; asignar los campos normalizados a columnas y confirmar el formato de fecha antes de importar. Las sugerencias se basan únicamente en nombres de columnas y no se aplican sin confirmación.

La primera fila no vacía de cada hoja/CSV es la cabecera. Se admiten cabeceras repetidas o vacías mediante identificadores estables c0, c1, etc. Para archivos con títulos o banners antes de la tabla, preparar una copia con la cabecera correcta y conservar también la fuente del cliente. No editar el original desde esta aplicación.

El usuario puede revisar filas aceptadas, rechazadas, advertencias y valores originales. El listado de eventos requiere seleccionar una versión de importación; no mezcla revisiones. Reenviar el mismo mapeo no duplica eventos. Cambiarlo genera una revisión independiente y conserva la anterior.

## Formatos y límites

| Límite | Comportamiento |
| --- | --- |
| .xlsx y .csv, hasta 20 MiB | Otros formatos y archivos vacíos se rechazan |
| 100 000 registros, 200 columnas, 20 hojas | Se rechaza el archivo completo al superar límites; sin truncamiento silencioso |
| 32 KiB por celda; 512 bytes por título de columna | Error explícito al excederlos |
| 200 MiB de ZIP expandido, 1000 partes | Validación previa a cargar el libro |
| 200 MiB de lectura JSONL derivada | Evita amplificación mediante cadenas compartidas de Excel |
| 120 segundos para interpretar un archivo | El proceso lector se termina si supera el tiempo |
| 8 trabajos pendientes más uno en ejecución | Respuesta 429 cuando la cola está llena |

Se cuentan también las filas vacías en el presupuesto de lectura, con un margen de hasta 20 cabeceras. Se informa por separado cuántas filas vacías se omitieron. La muestra muestra hasta 10 filas por hoja y 200 caracteres por celda; los datos completos se conservan en la fuente y en las filas importadas. No se garantiza rendimiento para cualquier archivo dentro de estos límites; un archivo costoso puede alcanzar el timeout.

CSV: UTF-8, UTF-16 con BOM y Windows-1252 (este último mediante selección explícita). Separadores coma, punto y coma, tabulación o barra vertical. La opción automática detecta BOM y estima el delimitador, mostrando la decisión en pantalla. Si la estructura no es la esperada, elegir las opciones explícitas y volver a cargar. Un registro con saltos de línea conserva línea inicial y final. Las filas con cantidad de columnas distinta se registran como rechazadas; comillas malformadas o errores de codificación rechazan el archivo completo.

XLSX: validación ZIP y XML con defusedxml, lectura read-only, dimensiones verificadas mediante las celdas reales. Rechazo de macros, contenido binario incrustado, cifrado, relaciones externas (incluidos hipervínculos externos) y entidades XML. No se ejecutan fórmulas ni se utilizan sus resultados cacheados. Una fórmula se conserva como texto, pero no se usa como campo normalizado. Las fechas tipadas por Excel se representan en ISO; el libro original conserva su representación exacta y sus estilos.

## Fechas y horas del archivo

No se solicita configuración horaria. Las fechas con referencia explícita se interpretan automáticamente; las que no la incluyen conservan la hora registrada, sin asignarles una ubicación. Se admiten ISO 8601, DD/MM/AAAA HH:mm:ss, MM/DD/AAAA HH:mm:ss y Unix en segundos/milisegundos.

Las fechas inválidas o ausentes se conservan con advertencias. Las horas sin referencia se comparan dentro de la misma importación del archivo, sin mezclar automáticamente relojes de archivos distintos. Las hojas de un mismo libro pueden importarse juntas. Los datos históricos y sus resultados se conservan; una revisión nueva usa el comportamiento actual.

Las IP inválidas se conservan con advertencia. Las filas idénticas se marcan como posibles duplicados y se conservan con sus referencias individuales.

## Trazabilidad y consistencia

Cada fuente utiliza un identificador aleatorio; el nombre proporcionado nunca se utiliza como ruta. Se conserva el archivo original y su SHA-256. Los eventos apuntan a caso, importación, hoja, fila y línea final. El detalle muestra columnas originales, valores, hash y configuración versionada de interpretación.

Se verifica el hash del original antes de cada trabajo y el de la lectura derivada antes de importar. La normalización se guarda en una sola transacción, en lotes de tamaño acotado. Si falla cualquier lote, se revierte toda la revisión; el trabajo queda fallido y no presenta eventos parciales como completos. Los conteos corresponden únicamente a las hojas elegidas: total = aceptadas + rechazadas; las advertencias son un subconjunto de las aceptadas.

Una carga repetida con mismo caso/hash/opciones reutiliza la fuente. Opciones CSV distintas generan otra interpretación de la misma fuente, identificada por otro registro. Los trabajos fallidos pueden reintentarse explícitamente; no se reintenta automáticamente un archivo hostil.

## Cola local y límites de despliegue

Esta entrega usa una cola local con estados durables en la base de datos, un consumidor y un subproceso lector cancelable. Se eligió este paso previo a Celery para mantener el arranque nativo en Windows sin Redis ni Docker. Ejecutar una sola instancia/proceso de API. Al reiniciar, trabajos pendientes o en ejecución se marcan fallidos para permitir una revisión y un reintento explícitos. No hay recuperación automática ni ejecución distribuida.

La infraestructura Celery/Redis de la arquitectura objetivo sigue pendiente. También están pendientes autenticación, autorización multiusuario, cuotas globales, purga/retención y escaneo antivirus. El subproceso lector no es una sandbox de sistema operativo ni impone un límite de RAM mediante el SO. La aplicación se limita a localhost; no publicar ni abrir túneles para datos de clientes. Ningún registro se envía a Ollama en esta fase.

Almacenamiento nativo: `.local/ingestion/`; Compose: volumen privado `ingestion_data`. Ninguna de estas rutas se publica como recurso estático. No subir archivos, filas ni capturas con información de clientes al repositorio.

## API implementada

Carga multipart con `file`, `encoding` y `delimiter`: `POST /api/v1/cases/{case_id}/files` devuelve 202 con archivo y trabajo. `GET /jobs/{id}` devuelve queued/running/succeeded/failed. `POST /jobs/{id}/retry` reintenta un trabajo fallido.

`GET /cases/{id}/files`, `GET /files/{id}/preview`, `GET /files/{id}/jobs` y `GET /files/{id}/imports` recuperan fuentes y su historial. `POST /files/{id}/imports` recibe hojas y mapeos, formato de fecha; devuelve el trabajo. `GET /cases/{id}/events?import_id=...` y `GET /imports/{id}/issues` admiten offset/limit (máximo 100). `GET /cases/{id}/events/{event_id}` recupera la evidencia. Todas estas rutas están bajo `/api/v1`.

Los endpoints comprueban existencia y pertenencia entre caso/importación/evento; eso no sustituye autorización por usuario, aún pendiente. El proxy de la interfaz admite solo rutas conocidas, valida el origen de las escrituras, limita los bytes reales de la carga y evita caché de los datos.
