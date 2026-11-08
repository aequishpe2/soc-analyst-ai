# Contrato analítico y API prevista

Estado: especificación; umbrales iniciales sujetos a evaluación con datos sintéticos y contexto del cliente.

Para los contratos efectivos, consultar INGESTION.md y DETECTION.md. El motor y sus rutas de análisis ya están implementados; informes, revisión auditable, purga y autorización multiusuario siguen pendientes.

## Entidades

| Entidad | Campos esenciales |
| --- | --- |
| Caso | id, organización, título, alcance, zona horaria, responsable, retención |
| Archivo | id, case_id, nombre original, ruta interna, SHA-256, tamaño, estado |
| Importación | id, file_id, hojas, mapeo versionado, filas aceptadas/rechazadas, advertencias |
| Evento | id, case_id, import_id, hoja, fila, timestamp original/UTC, tipo, resultado, usuario, host origen/destino, IP origen/destino, proceso, comando, event_id del proveedor, campos originales |
| Análisis | id, case_id, estado, versiones, configuración, cobertura, inicio/fin, error seguro |
| Hallazgo | id, analysis_id, regla/versión, título, severidad, confianza, estado de revisión, justificación, limitaciones |
| Evidencia | finding_id, event_id, campos relevantes y papel en la correlación |
| Grupo de investigación | id, hallazgos relacionados, entidades compartidas, intervalo, motivo de relación |
| Informe | id, análisis y revisión de origen, versión, estado borrador/revisado, hash del PDF |

Campos ausentes son null, nunca datos inferidos inventados. IP, hash y dominio observados son artefactos; solo se presentan como IoC si existe evidencia de su relación maliciosa. Un grupo de investigación no equivale a un incidente confirmado. El analista registra su decisión y justificación sin sobrescribir evidencias.

## Detecciones iniciales

| Regla | Condición inicial | Severidad propuesta | Limitación |
| --- | --- | --- | --- |
| Fuerza bruta | ≥10 fallos en 5 min por origen y usuario | Medio | Requiere fecha, resultado, origen y usuario |
| Password spraying | ≥10 usuarios distintos con fallo desde un origen en 10 min | Alto | Un proxy o servicio puede explicar el origen compartido |
| Éxito tras fallos | ≥5 fallos y luego éxito en 10 min, mismo usuario y origen | Alto | Indicio de acceso sospechoso, no prueba de compromiso |
| Acceso fuera de horario | Éxito fuera del calendario configurado | Bajo | Sin calendario, regla no evaluable |
| Cambio de privilegios | Evento explícito de asignación de rol/grupo privilegiado | Medio | Elevar riesgo solo con contexto o correlación justificados |
| Comando sospechoso | Patrón versionado en comando/proceso con coincidencia visible | Medio | Herramientas administrativas también pueden ser legítimas |
| Posible movimiento lateral | Accesos remotos exitosos de un usuario a ≥3 destinos en 10 min | Alto | Requiere tipo de acceso y destinos, puede ser administración |
| Desactivación de controles | Evento explícito de parada/deshabilitación de auditoría o protección | Alto | No inferirlo de la ausencia de logs |

Cada regla declara campos requeridos, clave de agrupación, ventana, manejo de duplicados, umbral, exclusiones y pruebas positivas/negativas. El informe distingue reglas evaluadas, no aplicables y no evaluables. La falta de hallazgos nunca se traduce en ausencia de compromiso.

El motor correlaciona dentro del mismo caso por usuario, origen, host y proximidad temporal; conserva aristas y razones. No unir eventos solo por una IP compartida. Separar grupos cuando no exista relación suficiente y presentar incertidumbre sobre el número de incidentes.

## Riesgo y confianza

Severidad y confianza son dimensiones distintas. Bajo: anomalía contextual limitada; Medio: actividad sospechosa que requiere investigación; Alto: secuencia sustentada con posible impacto significativo; Crítico: evidencia explícita y corroborada de impacto grave o compromiso de activos críticos. No asignar Crítico por una palabra clave o por la opinión del modelo.

La justificación identifica condición observada, activos afectados conocidos, contexto usado y límites. Impactos no observados se redactan como potenciales. Contexto desconocido no se rellena con supuestos. El analista puede cambiar severidad dejando autor, fecha y motivo auditables.

## API v1 propuesta

Todas las operaciones se limitan a casos autorizados. Listados con paginación, filtros permitidos y máximo de resultados. Fechas ISO 8601 con offset; IDs opacos. Errores con código, mensaje seguro y request_id.

| Método y ruta | Resultado |
| --- | --- |
| POST /api/v1/cases | Crear caso |
| GET /api/v1/cases | Listar casos accesibles |
| POST /api/v1/cases/{case_id}/files | Subir multipart; 202 con job_id tras validación inicial |
| GET /api/v1/jobs/{job_id} | Estado, progreso y errores; validar acceso al caso |
| GET /api/v1/files/{file_id}/preview | Hojas, columnas y muestra limitada autorizada |
| POST /api/v1/files/{file_id}/imports | Confirmar mapeo, hojas, formato de fecha y zona; 202 |
| GET /api/v1/cases/{case_id}/events | Consultar eventos y referencias originales |
| POST /api/v1/cases/{case_id}/analyses | Crear análisis con configuración versionada; 202 |
| GET /api/v1/analyses/{analysis_id}/findings | Hallazgos y cobertura |
| GET /api/v1/analyses/{analysis_id}/dashboard | Agregados del mismo análisis |
| PATCH /api/v1/findings/{finding_id}/review | Revisión con versión esperada para evitar sobrescrituras |
| POST /api/v1/analyses/{analysis_id}/ai-reviews | Revisión IA opcional con configuración explícita; 202 |
| POST /api/v1/analyses/{analysis_id}/reports | Crear instantánea de informe; 202 |
| GET /api/v1/reports/{report_id}/download | PDF con autorización y sin caché pública |
| DELETE /api/v1/cases/{case_id} | Solicitar purga autorizada y auditada; 202 |

Solicitudes que crean trabajos admiten clave de idempotencia. Estados: queued, running, succeeded, failed, cancelled. Las tareas repetidas no duplican resultados. Las importaciones fallidas no exponen conjuntos parciales como completos.

## Informe

Contenido: alcance, hashes de archivos, periodo, zona horaria, calidad y cobertura; resumen ejecutivo; hallazgos y sus evidencias por hoja/fila; explicación técnica; criticidad y confianza; impacto observado o potencial; grupos de investigación; plan de investigar, contener y remediar; recomendaciones; limitaciones y metodología/versiones.

Cada acción propuesta se vincula a un hallazgo y distingue recomendación de acción ejecutada. PDF generado desde una instantánea; incluir estado borrador/revisado y resultados de IA validados. Los errores de PDF no alteran hallazgos. No cargar imágenes, fuentes ni enlaces externos provenientes de logs.
