# Asistente de IA local

## Uso

1. Iniciar con `Iniciar-SOC.cmd` (Ollama y `qwen3:8b` deben estar instalados).
2. Abrir un caso, ejecutar o seleccionar un análisis completo y pulsar **Investigar hallazgo**.
3. Pulsar **Preparar borrador con IA**. Se consulta el estado sin bloquear la página.
4. Revisar explicación, criticidad, limitaciones y plan de investigación, contención y remediación.
5. Abrir las referencias citadas para comprobar archivo, hoja, fila y hash. La tabla conserva el conjunto completo de evidencias del hallazgo.

Cada hallazgo tiene un borrador persistente. Solicitudes repetidas devuelven el mismo trabajo. Un fallo permite reintentar; reiniciar el servicio marca trabajos interrumpidos como fallidos. No se modifican los hallazgos ni se confirma un incidente. La IA no se ejecuta automáticamente sobre todos los casos.

## Rigor y alcance de esta entrega

Se implementa composición restringida, no redacción libre ni un agente autónomo. Qwen3 organiza hechos y limitaciones ya comprobados, selecciona referencias y prioriza recomendaciones de un catálogo por regla. El servidor compone los párrafos en español a partir de esa selección. El modelo no puede introducir hechos nuevos, cambiar la criticidad, quitar limitaciones ni escribir comandos o acciones arbitrarias.

Comprobar que una referencia exista no demuestra que una frase generada esté sustentada. Por eso la salida admite identificadores de contenido permitido, nunca afirmaciones de texto libre. Se rechazan campos extra, identificadores desconocidos o repetidos, omisiones de hechos y ausencia de roles de evidencia necesarios (por ejemplo, fallos y éxito posterior).

El borrador conserva explícitamente la incertidumbre del motor. El impacto es potencial y las medidas de contención son condicionales. Todo resultado está pendiente de revisión; esta versión aún no registra aprobación o edición del analista. No hay un informe global ni exportación PDF todavía. No se ha medido utilidad operativa con casos reales ni precisión del modelo sobre un corpus SOC revisado.

## Privacidad y trazabilidad

- Proveedor cerrado a Ollama local, sin fallback externo, herramientas de shell ni acceso de red elegido por el modelo.
- Contexto mínimo: título de regla, severidad, confianza, explicación de la regla, limitaciones y recomendaciones. Las evidencias se representan por alias y roles.
- No se envían celdas originales, nombres de clientes o archivos, usuarios, IP, comandos, procesos, ni texto arbitrario de los registros. La correspondencia entre alias y evidencias permanece en la API.
- Se comprueba pertenencia al caso y al alcance, cantidad de evidencias y SHA-256 de los archivos antes y después de generar.
- Se conservan modelo, digest del modelo, versión de composición, huella de entrada (incluye catálogo, referencias, prompt y parámetros), selección y resultado validado. El modelo debe mantener su digest durante la generación.
- Se guardan contadores de tokens y duración si Ollama los devuelve. No se registran prompts ni respuestas rechazadas en logs.

## Presupuestos y recuperación

Un trabajo persistente por hallazgo, procesado por un consumidor de IA serial separado de la cola de importación. El flujo automático solicita todos los borradores y muestra su progreso; ver [AUTOMATIC.md](AUTOMATIC.md). Contexto de 4096 tokens, salida máxima de 512 tokens, solicitud máxima de 24 KiB, respuesta máxima de 16 KiB y plazo de inferencia de 180 segundos. La comprobación de disponibilidad del modelo tiene su propio timeout de cinco segundos. Máximo seis referencias candidatas con representación de los roles; no se presenta esa selección como el conjunto completo de evidencias.

Se usa temperatura 0 y semilla 17; esto reduce variación, sin prometer determinismo de inferencia entre equipos o versiones. La selección de evidencias es una ayuda de navegación, no una nueva detección ni una prueba de causalidad.

Si Ollama está caído, falta el modelo, cambia el archivo, se supera un presupuesto o la respuesta no es válida, el trabajo falla con un mensaje explícito y sin resultado parcial. El análisis determinista sigue disponible. Las nuevas importaciones pueden continuar mientras el consumidor de IA trabaja. El despliegue distribuido sigue pendiente.

## API

- `GET /api/v1/analyses/{analysis_id}/findings/{finding_id}/draft`: estado y borrador, o `draft: null`.
- `POST` a la misma ruta: crear o recuperar un trabajo; reintentar si falló. Respuesta 202, consultable mediante GET.

Los IDs de hallazgo deben corresponder al análisis. Los errores de cola se devuelven con 429, referencias ajenas con 404 y análisis incompletos con 409. La ruta web exige el mismo origen para POST.

## Verificación

Pruebas con proveedor falso y transporte HTTP simulado, sin necesitar Ollama en CI: ciclo de vida, idempotencia, referencias cruzadas, modificación del original, rechazo de afirmaciones extra con referencias válidas, referencias inexistentes, duplicados, omisión de limitaciones y roles, aislamiento de instrucciones maliciosas en celdas, cambio de modelo, proveedor caído, respuesta inválida, tamaño y truncamiento. La prueba real local utiliza únicamente el caso de demostración sintético.

Referencias oficiales de implementación: [salidas estructuradas de Ollama](https://docs.ollama.com/capabilities/structured-outputs) y [API de chat](https://docs.ollama.com/api/chat).

Fine-tuning y consultas autónomas sobre eventos quedan para una fase posterior, con datos autorizados, evaluación y necesidad demostrada.
