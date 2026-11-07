# Plan de desarrollo y aceptación

Las fases están ordenadas por dependencias. Ninguna funcionalidad se considera entregada solo por tener una pantalla.

## 1. Base ejecutable

Crear monorepo, Compose, configuración de ejemplo sin secretos, API de salud, migraciones iniciales y shell de interfaz en español. CI con lint, tipos, pruebas y escaneo de dependencias/secretos. Dependencias fijadas y guía de arranque desde clon limpio.

Aceptación: servicios saludables; migración reproducible sobre base vacía; CI verde; ningún secreto en archivos ni imágenes. Desarrollo ligado a localhost; despliegue compartido bloqueado hasta disponer de autorización comprobada.

## 2. Importación y evidencia

Implementar casos, CSV/XLSX, vista previa, mapeo, zona horaria y registro de errores. Crear fixtures exclusivamente sintéticos.

Aceptación: una fila mostrada conserva referencia verificable al archivo/hoja/fila y hash del original; fechas ambiguas requieren resolución; conteos de aceptadas/rechazadas cuadran; probar CSV con comillas/saltos, múltiples hojas, archivos corruptos, límites, fórmulas y contenido hostil; importaciones fallidas no parecen completas.

## 3. Motor analítico

Implementar las reglas de ANALYSIS_SPEC, cobertura, correlación y justificación de riesgo con configuración versionada.

Aceptación: para cada regla, casos positivos, negativos y en el límite del umbral/ventana; falsos positivos administrativos; ausencia de campos; mismos datos y configuración producen los mismos hallazgos; ningún hallazgo carece de evidencias; grupos separados para secuencias sin relación. Medir precisión/recobrado por regla sobre fixtures etiquetados, sin extrapolar a datos reales.

## 4. Dashboard y revisión

Filtros por análisis, criticidad, periodo, usuario y host; timeline, distribución de riesgos y tabla de evidencia. Revisión humana con historial.

Aceptación: gráficos y tabla concuerdan con la API bajo los mismos filtros; navegación por teclado, contraste legible, estados de carga/vacío/error y distinción visible entre severidad, confianza y revisión. No mostrar datos inventados para completar gráficos.

## 5. IA acotada

Implementar adaptador falso para pruebas y un proveedor configurable; herramientas de lectura, minimización, esquemas y validación de afirmaciones.

Aceptación: sin clave todo el análisis determinista funciona; probar referencias inexistentes, afirmaciones incorrectas con referencias válidas, instrucciones maliciosas dentro de logs, timeout, cuota, presupuesto y proveedor caído. Salidas sin soporte se rechazan. Los prompts no mezclan casos ni envían campos excluidos. Evaluar soporte factual, utilidad y costo con ejemplos revisados.

## 6. Informe y PDF

Implementar instantáneas, plantilla, descarga y pruebas de extremo a extremo desde la carga.

Aceptación: PDF legible con caracteres españoles, tablas extensas, saltos de página y evidencias largas; revisión visual de renderizados; conteos, severidades y referencias iguales a la instantánea. Un caso sin hallazgos explica cobertura y limitaciones. La caída de IA no impide exportar un informe basado en reglas.

## 7. Preparación para despliegue compartido

OIDC, roles, aislamiento por organización, retención/purga, TLS, auditoría, límites, backup/restauración y observabilidad sin datos sensibles.

Aceptación: pruebas de acceso cruzado en API, trabajos y descargas; usuario lector no modifica; restauración probada; purga verificada en derivados y estrategia de respaldos documentada. Medir recursos con el máximo de archivo soportado y publicar límites reales, no promesas de rendimiento.

## Evolución

Ampliar adaptadores de proveedores, reglas de persistencia, creación de cuentas, manipulación de auditoría, actividad DNS/red y posible exfiltración cuando existan campos adecuados. Incorporar reglas personalizadas revisadas, inteligencia de amenazas opcional con procedencia/fecha y evaluación de anomalías con baseline suficiente. Fine-tuning solo tras demostrar una mejora medible respecto del modelo base, con dataset autorizado y separado de casos de evaluación.

## Definición de terminado

Código revisable, contratos y documentación actualizados, pruebas pertinentes aprobadas, errores manejados, evidencias verificables, sin secretos ni datos de clientes y limitaciones declaradas. No presentar la herramienta como sustituto de una investigación completa o como certificación de cumplimiento.
