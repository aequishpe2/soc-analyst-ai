# Informe técnico y PDF

Desde el dashboard, abrir **Informe técnico → Preparar informe**. Revisar el resumen, fuentes, cobertura, hallazgos y anexo. Los datos de analista, cliente, consultora y referencia son opcionales; nunca se deducen de los registros. Pulsar **Descargar informe PDF**. Funciona también desde la pantalla de análisis avanzado.

## Formatos de descarga

**Para cliente · conciso** es el formato predeterminado desde la versión `technical-report-2`. Presenta resumen ejecutivo, todos los hallazgos con criticidad justificada, impacto posible, limitaciones y acciones, correlaciones, cobertura resumida, recomendaciones y fuentes verificadas. Cada hallazgo cita archivo, hoja y filas de evidencia. Los rangos solo agrupan filas consecutivas existentes; no incluyen huecos. Evita portada aislada, explicaciones repetidas, configuración interna y volcado de cada celda. No elimina hallazgos ni cambia la clasificación. Los caracteres fuera de Latin-1 se representan como `[U+XXXX]`, igual que en el formato técnico.

**Técnico completo · con anexo de registros** conserva el detalle ampliado descrito abajo y la opción de incluir explicaciones IA. El formato para cliente resume los hechos del motor; las explicaciones ampliadas de IA permanecen en la aplicación y en el formato técnico. La vista previa permite consultar el detalle completo con cualquiera de los dos formatos.

En el caso local verificado, el formato para cliente ocupa **6 páginas frente a 56**, conservando los 20 hallazgos y las referencias a las 80 evidencias. La extensión depende del caso; no se impone un límite de páginas que recorte resultados.

## Contenido del formato técnico completo

- Portada confidencial y huella de la instantánea.
- Resumen ejecutivo con registros, hallazgos por criticidad, evidencias únicas y grupos para investigar.
- Alcance, metodología, fuentes originales y SHA-256 verificado al exportar.
- Cobertura de cada regla, exclusiones y limitaciones.
- Todos los hallazgos: explicación, hechos observados, justificación de criticidad, prioridad, confianza, periodo, referencia ATT&CK, limitaciones, impacto posible y acciones de investigación, contención y remediación.
- Explicaciones de IA local completadas y validadas, cuando se elige incluirlas; modelo, digest y huella de entrada por explicación.
- Grupos relacionados y motivos de sus conexiones. No equivalen a incidentes confirmados.
- Recomendaciones preventivas, identificadas como recomendaciones y no como deficiencias demostradas.
- Anexo con todos los registros de evidencia distintos citados por los hallazgos, sus campos normalizados no vacíos, archivo, importación, hoja, fila e identificador. El archivo original completo permanece en el explorador.
- Configuración y versiones del análisis.

## Garantías y límites

La exportación usa el análisis completo seleccionado; ignora los filtros de visualización y la paginación del dashboard. No ejecuta otra inferencia, no cambia los hallazgos ni añade información al caso. Sigue disponible cuando Ollama está detenido; indica cuántas explicaciones estaban disponibles. Se puede excluir la IA.

El servidor valida el estado del análisis, pertenencia y cantidad de las referencias, y hashes de los archivos originales. Ante fuentes alteradas, evidencia incompleta o análisis pendiente/fallido, rechaza la descarga. El contenido de las celdas se trata como texto literal, nunca como HTML, instrucciones o código ejecutable.

La vista previa devuelve una huella del contenido. La descarga enviada desde la interfaz exige esa misma huella: si termina una explicación IA entre ambos pasos, responde 409 y solicita actualizar la vista previa. La huella identifica el contenido analítico; los datos de portada y el instante de exportación pueden variar. No es una firma digital. La respuesta PDF lleva además su SHA-256 y la huella de la instantánea en las cabeceras de la API.

Los PDF muestran una leyenda neutral de **Confidencial**, sin la etiqueta de borrador o revisión pendiente. La aplicación todavía no registra una aprobación del analista: retirar esa leyenda no acredita una revisión. Contención y remediación son propuestas condicionadas a validar contexto y autorización. No se confirma impacto ni se asigna un número de incidentes automáticamente.

Límites de esta primera versión: 2000 hallazgos, 20 000 referencias, 20 MiB de contenido y 20 MiB de PDF. Si se superan, se pide reducir el alcance; no se recortan hallazgos silenciosamente. La generación es síncrona, en un hilo del servidor; el proxy espera hasta 30 segundos. No se ha validado el rendimiento en el máximo admitido. Para investigaciones muy grandes queda pendiente una cola dedicada de exportación.

Se utiliza ReportLab, sin binarios de sistema para generar el PDF. La tipografía PDF básica conserva caracteres españoles; los caracteres fuera de Latin-1 se representan de forma explícita como `[U+XXXX]`. Los valores largos se dividen en bloques continuados, sin eliminar caracteres. Los campos normalizados vacíos se omiten del anexo.

No se persiste el PDF en el servidor al descargar: el usuario conserva la copia exportada. No hay catálogo de informes ni firma o aprobación auditada en esta versión. Las respuestas no se almacenan en caché; los informes y archivos de clientes se excluyen de Git.

## API

- `GET /api/v1/analyses/{id}/report`: instantánea completa para vista previa, versión `technical-report-2` y `snapshot_hash`.
- `POST /api/v1/analyses/{id}/report/pdf`: descarga binaria. JSON opcional por campos: `analyst`, `client`, `organization`, `reference`, `format` (`client` por defecto o `technical`), `include_ai` (por defecto true; aplicable al formato técnico), `snapshot_hash`. El cuerpo JSON es obligatorio; usar `{}` para los valores por defecto. Si se proporciona la huella, debe coincidir.

El proxy web admite únicamente estas rutas adicionales, conserva la comprobación de origen para POST, limita la respuesta binaria y fija el tipo y nombre de descarga.

## Verificación

Pruebas con datos sintéticos: PDF multipágina, caracteres españoles, todos los hallazgos y referencias, filtros sin efecto en el informe, caso sin hallazgos, metadatos inválidos, fuente alterada, evidencia incompleta, IA opcional, cambio de instantánea y celdas largas con contenido hostil/Unicode. Se extrae el texto con pypdf y se revisan también las páginas renderizadas con Poppler; la extracción de texto por sí sola no verifica el diseño.
