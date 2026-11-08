# Carga y análisis automáticos

## Uso

Desde la portada o desde un caso, arrastrar un archivo `.xlsx` o `.csv`, o pulsar el área de carga. Límite de 20 MB. La portada crea una investigación con el nombre del archivo; dentro de un caso se conserva ese caso.

La aplicación carga el original, lee sus hojas, propone columnas y formato de fecha, importa registros y ejecuta detección/correlación. Al terminar abre `/cases/{id}/overview`, con navegación a resumen, hallazgos, explorador de eventos, correlaciones, explicaciones de IA y ajustes avanzados. El diseño usa una paleta azul y se adapta a ventanas estrechas.

Ollama prepara automáticamente una explicación por cada hallazgo. La detección y el dashboard se muestran antes de que termine toda la IA. Los contadores informan explicaciones listas, activas, pendientes y fallidas. La lista de explicaciones está paginada a veinte, pero se solicitan todos los hallazgos, sin truncarlos a la primera página. El usuario puede seguir explorando o recargar la página; el estado se conserva en SQLite.

## Interpretación y rigor

Versión del flujo: `automatic-2`, con motor contextual 2.0 y normalizador 4. Las columnas y el perfil elegidos se conservan en las decisiones. El analista puede consultarlos desde **Cómo se interpretó el archivo automáticamente**. Ver [fuentes, reglas y prioridades](DETECTION_V2.md).

- Las fechas se comprueban en todas las filas. Formatos día/mes ambiguos o mezclados requieren una revisión explícita. Las unidades epoch solo se proponen para magnitudes reconocibles de diez o trece dígitos. Fechas sin referencia conservan su reloj; no se solicita una ubicación.
- Se usan las sugerencias conservadoras de `mapping.py`. La asignación de `Destination` sigue basada en la muestra y debe revisarse si una columna mezcla clases más adelante; no se certifica el esquema de todo el archivo.
- El perfil automático interpreta cada registro según proveedor, canal y campos explícitos. Esto permite archivos mixtos Windows, PowerShell, Proxy e IIS dentro de los formatos admitidos. La inferencia queda visible y no certifica la procedencia. Un código numérico sin contexto no autoriza esa interpretación.
- Si hay hojas sin columnas reconocibles o un proveedor indeterminado, el flujo queda en `needs_review` y ofrece abrir los ajustes. No se fabrica un dashboard de alertas positivas para evitar ese estado.
- No se presupone un horario laboral ni se cambian umbrales para producir más alertas. El dashboard informa cobertura parcial, condiciones no evaluables y datos ausentes. Un grupo no equivale a un incidente confirmado.
- La IA sigue el contrato de [composición restringida](AI.md): organiza explicaciones y recomendaciones permitidas, sin crear hechos ni reclasificar riesgos de forma libre. Los registros originales y sus comandos no se envían al modelo.

## Persistencia y ejecución

Migraciones 0006 y 0007: `automatic_runs`, índice de borradores pendientes y unicidad por archivo/versión. Las solicitudes de la misma versión recuperan su estado; una versión nueva conserva el historial y genera su propia revisión. Los fallos pueden reintentarse explícitamente. El original se verifica mediante SHA-256 antes de procesar.

La cola local de ocho posiciones procesa lectura, importación y detección. Un segundo consumidor procesa los borradores de IA uno por vez, priorizando Críticos y Altos. Esto evita bloquear nuevas importaciones. Cada borrador mantiene 512 tokens de salida y 180 segundos máximos; muchos hallazgos pueden tardar más en completarse, con progreso visible.

Se admite una sola instancia de API. Al reiniciar, los trabajos interrumpidos se marcan fallidos; no aparecen como completados. Se puede reintentar el flujo o las explicaciones desde la interfaz. Si falta Ollama o el modelo, el análisis determinista termina y las explicaciones se pueden solicitar al recuperar el servicio. No hay fallback externo.

## API

- `POST /cases/{case_id}/files/{file_id}/automatic`: iniciar/recuperar el flujo, o reintentar un fallo.
- `GET /cases/{case_id}/automatic/{run_id}`: fase, estado, decisiones y referencias al análisis/importación.
- `GET /analyses/{analysis_id}/assistant?offset=0`: contadores globales y veinte explicaciones/hallazgos.
- `POST /analyses/{analysis_id}/assistant`: solicitar los borradores que falten o reintentar fallidos.

Todas las rutas tienen prefijo `/api/v1`, verifican pertenencia y pasan por la lista permitida del proxy web. La aplicación sigue siendo local y no ofrece autenticación multiusuario ni despliegue compartido.

## Pendiente

Informe técnico global y PDF, aprobación humana auditable, adaptadores adicionales de proveedores, validación de rendimiento máximo y evaluación de calidad SOC sobre casos revisados. La automatización no implica soporte completo de todos los SIEM ni detección de todas las técnicas.
