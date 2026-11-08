# Verificación de la base local

## Matriz MITRE ATT&CK - 8 de noviembre de 2026

- **223 pruebas aprobadas** en la batería completa. Se mantiene el aviso existente de deprecación de Starlette/httpx en TestClient.
- Catálogo oficial Enterprise 20.1: 15 tácticas y 16 referencias utilizadas por el motor; fuente y SHA-256 del bundle registrados. La referencia retirada T1562 no se reasigna automáticamente.
- Matriz verificada con filtros compartidos, conteos únicos, aislamiento entre casos, estados vacíos/no evaluables, referencias desconocidas/retiradas, validación de técnica y correspondencia con la instantánea del informe.
- Prueba en navegador: selección T1490, filtrado a un hallazgo y apertura de su evidencia original con SHA-256. Retirada del filtro y navegación de la matriz verificadas. Captura y datos de verificación privados en `.local`, excluidos de Git.
- En el caso local: 20 hallazgos; 18 con referencia activa, 2 sin técnica asignada y 10 técnicas distintas relacionadas. Los conteos de las columnas no se suman como incidentes.
- Matriz compacta incluida en los dos formatos PDF. El formato para cliente mantiene **6 páginas** y todos sus hallazgos y referencias. Revisión visual de la tabla MITRE y trazabilidad; no reaparece la leyenda de borrador eliminada.
- Ruff, formato, TypeScript y compilación de producción aprobados. No hay dependencias ni migraciones nuevas. Ver [MITRE.md](MITRE.md).

## Informe técnico y PDF - 8 de noviembre de 2026

Actualización de presentación: el formato predeterminado para cliente se redujo de 56 a **6 páginas** en el caso local, manteniendo los 20 hallazgos y las referencias exactas a las 80 evidencias. Se revisaron visualmente las seis páginas y se comprobó la descarga mediante el proxy de la aplicación. **Nueve pruebas de informes aprobadas**, incluidas compresión de filas sin añadir huecos, conservación de hallazgos y selección/validación del formato. Ruff, formato y compilación con TypeScript aprobados. El formato técnico completo permanece disponible como opción.

- Batería completa: **216 pruebas aprobadas**, incluidas siete pruebas nuevas del informe. Persiste el aviso previo de deprecación de Starlette/httpx en TestClient.
- Ruff, formato Python, TypeScript, Prettier y compilación de producción aprobados. Dependencias de generación y extracción fijadas en `uv.lock`; no se requiere una migración nueva.
- Generación sobre el análisis local: 20 hallazgos, 80 evidencias distintas y 20 explicaciones IA, sin cambios en las prioridades. Se verificó por extracción que todos los identificadores de hallazgo y evidencia aparecen en el PDF. Documento de 56 páginas, con anexo completo y configuración. Los datos, resultados y capturas permanecen fuera de Git.
- Revisión visual con Poppler de portada, cobertura, hallazgo crítico, anexo y cierre. Ajustados los encabezados y el inicio de la sección de trazabilidad para evitar encabezados aislados y un cierre de pocas líneas.
- Descarga real desde el navegador mediante el proxy web y la API; vista previa, metadatos opcionales, inclusión de IA y conteos comprobados. Servicios locales reiniciados con la versión actual.

Ver [REPORTS.md](REPORTS.md) para garantías y límites. No se validó el rendimiento en el máximo de referencias ni la ejecución remota de GitHub Actions. La exportación no implica revisión o aprobación humana.

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

## Dashboard interactivo

Dashboard con criticidad, reglas, distribución diaria por fecha de inicio y principales usuarios/equipos. El backend comparte filtros entre gráficos y lista y agrega sobre todo el análisis, independientemente de la paginación. Sin dependencias ni migraciones nuevas.

- **153 pruebas aprobadas**: 133 existentes y veinte nuevas. Verifican coherencia entre agregados y lista, filtros combinados, fechas inclusivas, hallazgos sin fecha, páginas adicionales, referencias compartidas sin duplicar eventos, entidades deduplicadas por hallazgo, coincidencia de usuario/equipo en el mismo evento, entradas inválidas, grupos ajenos y análisis incompletos.
- Ruff, formato Python, tipos, compilación de producción y Prettier aprobados.
- Navegador sobre el caso sintético: vista inicial de siete hallazgos, 27 registros de evidencia únicos y tres grupos; filtro Alto a cuatro hallazgos; combinación con regla de éxito tras fallos, día, usuario y equipo a un hallazgo y once evidencias. Estado sin coincidencias y restablecimiento comprobados. Captura `.local/dashboard-verified.png`, excluida de Git.

Los siete hallazgos corresponden a la ejecución de demostración seleccionada, sin calendario; la ejecución histórica con calendario conserva sus ocho hallazgos. No se modifican resultados para completar los gráficos. La prueba visual se realizó en escritorio; el diseño incluye reglas adaptables, pero esta entrega no acredita una verificación visual móvil. Rendimiento máximo, PostgreSQL, revisión humana auditable e informe global/PDF siguen pendientes.

## Formatos nuevos y análisis no evaluables

Se centralizaron las sugerencias de encabezados en la API y se agregó reconocimiento de `Process_CommandLine`, clasificación revisable de `Destination` y sugerencia de perfil basada en proveedor o combinación de canal/ID/descripción. No se deduce una técnica de texto descriptivo arbitrario ni un proveedor por su ID numérico solo.

**160 pruebas aprobadas**, incluyendo siete pruebas nuevas. La regresión reproduce un export Windows sintético: trece filas, importación incompleta con cero hallazgos y cero reglas evaluables, nueva revisión con mapeo completo y perfil explícito con cuatro hallazgos respaldados. Se verifica que el original y los resultados históricos no cambien; códigos solos, instrucciones en descripciones, fórmulas, columnas ambiguas y destinos mixtos no activan inferencias automáticas.

El dashboard ahora distingue actividad importada, cero coincidencias y ausencia de reglas evaluables. Los cambios también se comprobaron en una revisión local del archivo señalado por el usuario; sus datos y resultados permanecen fuera de Git. Compilación, tipos, Ruff y formato aprobados. No se alteraron reglas ni umbrales para incrementar hallazgos.

## Carga automática y vista azul

Migración 0006, flujo `automatic-1`, consumidor de IA separado y ruta `/cases/{id}/overview`. La portada y el explorador de cada caso ofrecen carga automática; la importación manual se conserva como opción avanzada.

- **172 pruebas aprobadas**: 160 anteriores y doce del flujo automático. Incluyen CSV y XLSX, creación de análisis y todos sus borradores, idempotencia, fechas ambiguas, proveedor indeterminado, archivo modificado, columnas desconocidas, cola llena, pertenencia al caso, Ollama caído, recuperación tras reinicio e importación concurrente mientras el modelo espera.
- Ruff, formato Python, tipos, compilación de producción y Prettier aprobados. Migraciones hasta 0006 y comprobación de esquema desde SQLite vacío aprobadas; no hay dependencias nuevas.
- Prueba completa en navegador con CSV exclusivamente sintético: carga desde la portada, navegación automática al caso, trece eventos, cuatro hallazgos (dos Altos y dos Medios), trece evidencias únicas y un grupo de investigación. Sin selección manual de columnas, perfil, fechas ni ejecución individual de IA.
- Ollama/Qwen3:8b completó las cuatro explicaciones automáticamente. La vista recuperó `4 de 4` listas, sin pendientes ni errores, después de reiniciar los servicios y recargar.
- La ventana de aproximadamente 714 píxeles se comprobó sin desbordamiento horizontal. Se corrigió la interacción entre los estilos compartidos y la vista adaptable. Captura `.local/automatic-blue-verified.png`, excluida de Git. No se ajustó el viewport para la captura.

No se generó IA automáticamente sobre casos anteriores del usuario durante esta prueba. El flujo nuevo opera sobre la carga que se le solicita. La clasificación conserva las reglas y evidencias existentes; no implica detección universal ni confirmación automática de incidentes. PDF e informe global siguen pendientes.

## Motor contextual 2.0 y prioridades explicables

Motor `2.0.0`, catálogo de 19 reglas `soc-context-1`, normalizador 4, flujo `automatic-2` y composición IA `grounded-outline-2`. La migración 0007 conserva versiones de flujo por archivo en lugar de reutilizar un resultado antiguo bajo reglas nuevas.

- **209 pruebas aprobadas**, incluyendo las anteriores y 37 verificaciones adicionales de interpretación y reglas contextuales. Positivos y negativos sobre recuperación, tareas, servicios, compresión, PowerShell, peticiones web, volumen POST, ráfagas distribuidas y relaciones remotas; separación entre relojes, origen/canal insuficiente, metadatos contradictorios, resultados fallidos, cadenas citadas como texto y consultas malformadas. La prioridad de tareas/servicios inspecciona la acción o el binario configurado, sin elevarla por una ruta en una descripción ajena.
- Se verifica que 4672 no se declare escalamiento por sí solo, que un ID numérico no identifique al proveedor, que GET no se acumule como POST y que una orden fallida no reciba la prioridad Crítica reservada a la condición explícita de recuperación.
- La prueba de versionado demuestra que un flujo nuevo no reutiliza ni sobrescribe una ejecución anterior. Migración y `alembic check` desde base vacía aprobados; Ruff, formato, tipos y compilación de producción aprobados. No se agregaron dependencias.
- La revisión del archivo autorizado del usuario se conserva por separado. Se comprobaron pertenencia, hash de evidencias, orden por prioridad, conteos de dashboard y hallazgos, y finalización de todas las explicaciones con Ollama. Datos, IDs, resultados privados y capturas permanecen en `.local`, fuera de Git.

El nivel de prioridad expresa urgencia para investigar, no confirma un incidente ni el efecto de una orden. Las referencias ATT&CK orientan la investigación. Estas pruebas no acreditan precisión universal, cobertura de todos los SIEM ni rendimiento al máximo de archivo. Informe global/PDF, aprobación auditable y evaluación de calidad sobre un corpus independiente siguen pendientes.
