# Verificación de la base local

Verificado el 7 de noviembre de 2026 sobre Windows, con Node 24 y Python 3.12 administrados dentro de `.tools/` (ignorado por Git).

| Comprobación | Resultado |
| --- | --- |
| API: pytest | 8 pruebas aprobadas |
| Ruff y formato Python | Aprobados |
| Migración sobre SQLite vacío y `alembic check` | Aprobados |
| Next.js: build y TypeScript | Aprobados |
| npm audit y pip-audit | Sin vulnerabilidades conocidas reportadas en esta ejecución |
| Navegador | Creación de caso sintético y persistencia tras recargar/reiniciar servicios verificadas |
| Ollama apagado | La gestión de casos sigue disponible |

La revisión en navegador detectó y permitió corregir una comparación de origen del proxy y el tratamiento de timestamps UTC de SQLite. La fecha de creación se muestra en la zona del caso. La base de prueba, capturas y herramientas quedan excluidas de Git.

## Instalación nativa y modelo local

Ollama 0.40.15 se preparó desde el archivo oficial de Windows x64, con verificación SHA-256 contra el digest de su release. Qwen3-8B se descargó (aproximadamente 5,2 GB) al directorio privado `.local/models`. Ollama registró `cloud disabled: true` y escuchó solamente en 127.0.0.1:11434. Se detectaron gráficos Intel integrados; la prueba usó CPU.

La prueba sintética `Responde solamente LOCAL_OK.` devolvió `LOCAL_OK`, completada en 6,29 segundos con 3 tokens generados. Es una prueba de instalación e inferencia, no un benchmark representativo ni una evaluación de calidad SOC. Los resultados quedan en `.local/ai-smoke.json`, fuera de Git.

Los scripts Start/Stop/Test se ejecutaron con Windows PowerShell. Se verificó detener e iniciar los tres servicios conservando el modelo y la base local. Para permitir los scripts locales se habilitó, con autorización, RemoteSigned en CurrentUser de Windows PowerShell; no se modificaron políticas corporativas ni la configuración de otros usuarios.

Pendiente de verificar: Docker Compose, PostgreSQL real, aceleración de hardware y ejecución remota de GitHub Actions. Docker no está instalado; no es requisito del arranque nativo de esta fase. Las pruebas usan SQLite; no sustituyen una integración con PostgreSQL. Starlette emite un aviso de deprecación sobre su integración de pruebas con httpx; las pruebas pasan y la API usa httpx únicamente para el diagnóstico local de Ollama.

La infraestructura incluye CI para comprobaciones y escaneo de secretos. Su configuración en el repositorio no equivale a una ejecución remota aprobada.

## Importación de Excel y CSV (fase 2)

- 41 pruebas de API, lector, normalización y recuperación aprobadas. Incluyen CSV multilínea, UTF-8/UTF-16/Windows-1252, múltiples hojas XLSX, fórmulas, fechas ambiguas/inexistentes por DST, duplicados, límites de bytes/columnas/celdas, XML con DTD, partes ZIP inseguras y cambios de hash.
- Se provocó un fallo después del primer lote de 500 eventos y se comprobó que la transacción no conserva eventos ni una revisión parcial.
- Next.js, TypeScript, Ruff y comprobación de formato aprobados. Auditorías npm y pip sin vulnerabilidades conocidas reportadas en la ejecución.
- La migración 0002 se aplicó en la instalación local y en la base de prueba; Alembic no detectó diferencias con los modelos.
- Navegador: creación del caso sintético, carga y vista previa CSV con mapeos sugeridos comprobadas. Las comprobaciones restantes se hicieron por HTTP para no interferir con el uso simultáneo de la interfaz.
- HTTP a través del proxy real: 4 registros sintéticos aceptados, 2 sin hora UTC válida, duplicado preservado, evidencia multilínea y SHA-256 verificados; escritura con origen externo rechazada (403).

No se midió el rendimiento máximo de 100 000 registros ni se probó esta fase en PostgreSQL/Compose. El lector impone límites y un timeout, pero no es una sandbox de SO ni limita RAM a nivel del sistema. Consultar INGESTION.md para los límites y el alcance local de la cola.

## Detección y correlación (fase 3)

- Motor determinista 1.0.1, catálogo soc-local-1, normalización ampliada versión 2. Sin nuevas dependencias ni envío de registros al modelo.
- 106 pruebas aprobadas en la suite completa. Cubren las ocho reglas, umbrales y ventanas inclusivas, orden temporal estricto, calendarios, falsos positivos administrativos, semántica Windows, campos ausentes, contradicciones, fuentes sin identidad válida, exclusiones, duplicados, determinismo y cierre de evidencias dentro del alcance.
- Pruebas de persistencia: fallos al insertar evidencias revierten grupos/hallazgos; referencias externas o hallazgos sin evidencia se rechazan; fuentes modificadas bloquean el análisis; los trabajos interrumpidos se recuperan mediante reintento; dos lecturas del mismo original no pueden combinarse.
- Catálogo sintético etiquetado de 11 escenarios: 8 coincidencias de regla esperadas, 0 coincidencias adicionales y 0 omisiones (precisión/recobrado 1.0 únicamente en ese catálogo). No es una medición de precisión general ni validación con incidentes reales.
- Next.js, TypeScript, Ruff y formato aprobados. La migración 0003 se verificó desde una base vacía y se aplicó a la instalación local sin diferencias con los modelos.
- API/proxy real: caso de demostración separado, 29 registros de origen, 28 distinguibles, 1 copia preservada, 8 hallazgos y 4 grupos; distribución Crítico 0, Alto 4, Medio 3, Bajo 1. Referencias, hashes y pertenencia al alcance verificadas; origen externo de escritura rechazado.
- Navegador: selección de alcance/calendario, ejecución, filtros Alto + éxito tras fallos, apertura del hallazgo y consulta del registro original de éxito con SHA-256 verificadas. Los datos de prueba y las capturas permanecen en .local, fuera de Git.

Los cuatro grupos de demostración no se presentan como cuatro incidentes. No se realizaron análisis automáticos sobre los archivos del usuario. Siguen pendientes PostgreSQL/Compose, rendimiento máximo, fuentes SIEM adicionales, revisión humana auditable, gráficos avanzados, agente de IA e informe PDF. GitHub Actions está configurado, pero no se reporta una ejecución remota como aprobada sin haberla observado.

## Simplificación de fechas del archivo

Se eliminaron los controles y referencias de configuración horaria de casos, importación, calendarios, listas y detalles de configuración. No se solicita ese dato al cliente. Las configuraciones históricas se conservan internamente y no se muestran como opciones vigentes.

Motor 1.1.0, reglas soc-local-2 y normalización 3: fechas con referencia explícita se interpretan automáticamente; las demás conservan su hora sin asignarles una ubicación. Las comparaciones entre archivos exigen referencias comparables; las horas no calificadas se comparan dentro de su importación. Los calendarios usan la hora registrada. Los análisis históricos no se sobrescriben ni se reejecutan bajo una versión distinta.

112 pruebas aprobadas, incluyendo creación/importación/calendario sin el dato, ausencia del campo en los esquemas públicos y separación de relojes de archivos distintos. Compilación, tipos, formato y migración 0004 desde base vacía aprobados. Esta modificación no elimina ni cambia los archivos originales.

## Asistente IA local por hallazgo

Implementación de composición restringida `grounded-outline-1`, persistencia separada en `ai_drafts` y migración 0005. Qwen3 selecciona y organiza contenido permitido; la API compone el borrador sin aceptar afirmaciones nuevas. El resultado determinista no cambia.

- **133 pruebas aprobadas**: 112 existentes y 21 nuevas sobre IA. Se comprueban ciclo de vida, idempotencia, privacidad, aislamiento de instrucciones en celdas, pertenencia de evidencias, integridad de archivos, proveedor caído y reintentos, cambio de modelo, roles de evidencia, afirmaciones adicionales con referencias válidas, respuesta malformada, tamaño, tokens truncados, tiempo y contexto máximos, cola llena y reinicio.
- Ruff, formato Python, TypeScript, compilación de producción y Prettier aprobados. Migraciones hasta 0005 sobre SQLite vacío y `alembic check` aprobados. Sin dependencias nuevas.
- Prueba real mediante proxy web/API/Ollama en el caso sintético: borrador de asignación de privilegios completado en **34,58 segundos**, 396 tokens de entrada y 57 de salida reportados por Ollama. Modelo `qwen3:8b`, digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`. Se verificaron severidad, contenido permitido y hash de una evidencia original. Es una prueba funcional, no un benchmark de calidad SOC.
- Navegador: generación real del borrador de éxito tras fallos y apertura de su evidencia de acceso exitoso (fila 12) con SHA-256. Captura `.local/ai-draft-verified.png` y comprobación técnica `.local/ai-workflow-smoke.json`, excluidas de Git.

No se generaron borradores automáticamente sobre datos reales del usuario. Siguen pendientes evaluación con casos SOC revisados, aprobación humana auditable, consultas autónomas del agente, dashboard gráfico, informe global y PDF. La prueba local no acredita una ejecución remota de GitHub Actions.
