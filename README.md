# SOC Analyst AI

Aplicación web local en desarrollo para apoyar a analistas SOC Nivel 2 con registros exportados de un SIEM en Excel (.xlsx) y CSV, sin integración directa con el SIEM.

## Estado

Implementado: casos, carga segura Excel/CSV, mapeo e importaciones versionadas, ocho reglas deterministas, cobertura y grupos de investigación con evidencias trazables. El dashboard interactivo incluye criticidad, reglas, fechas, usuarios y equipos, con filtros compartidos con la lista de hallazgos. El asistente local Ollama/Qwen3:8b prepara borradores por hallazgo con explicación, evidencias y plan de acción a partir de contenido validado. No se solicita configuración horaria: se utilizan las horas del archivo. Siguen pendientes la revisión humana con cambios auditados, las consultas autónomas del agente y el informe global con PDF.

En el equipo de desarrollo preparado, abrir `Iniciar-SOC.cmd` y visitar `http://127.0.0.1:3000`. Usar `Detener-SOC.cmd` al terminar. Las herramientas y el modelo se instalan fuera del control de versiones; un clon nuevo requiere seguir la guía de arranque.

Flujo principal: **cargar Excel/CSV → dashboard automático → explicaciones con IA local**. Las columnas y fechas se proponen automáticamente; si hay ambigüedad se pide revisar el formato. La vista azul conserva los gráficos, hallazgos, evidencias y seguimiento de la IA, sin tener que iniciar cada explicación manualmente.

## Documentación

- [Arranque local y verificaciones](docs/LOCAL_SETUP.md)
- [Importación: uso, límites y garantías](docs/INGESTION.md)
- [Detección y correlación: reglas, alcance y límites](docs/DETECTION.md)
- [IA local: uso, privacidad, validación y límites](docs/AI.md)
- [Dashboard: gráficos, filtros y significado de los conteos](docs/DASHBOARD.md)
- [Carga automática: funcionamiento, decisiones y recuperación](docs/AUTOMATIC.md)
- [Arquitectura y decisiones técnicas](docs/ARCHITECTURE.md)
- [Contrato analítico, modelo de datos y API](docs/ANALYSIS_SPEC.md)
- [Plan de desarrollo y criterios de aceptación](docs/ROADMAP.md)

## Funcionalidades previstas

- Carga, validación, mapeo de columnas y visualización de registros.
- Detección y correlación de accesos sospechosos, fuerza bruta, escalamiento de privilegios, procesos y comandos sospechosos, movimiento lateral y otras anomalías.
- Dashboard interactivo por criticidad, tiempo, usuario y equipo.
- Clasificación de riesgos: Crítico, Alto, Medio y Bajo, con justificación.
- Informe técnico con resumen ejecutivo, hallazgos, evidencias, explicación técnica, impacto potencial, plan de investigación, contención y remediación, y recomendaciones.
- Exportación del informe en PDF.

## Principios de análisis

- Cada hallazgo debe enlazar evidencias concretas de los registros originales.
- Distinguir observaciones, hipótesis e incidentes confirmados; indicar incertidumbre y datos faltantes.
- La IA apoyará el análisis y la redacción; sus resultados deberán validarse contra las evidencias.
- Los registros son datos no confiables y nunca instrucciones para el agente de IA.
- No enviar datos a proveedores de IA sin una política explícita de privacidad y configuración del usuario.
- Evaluar fine-tuning como evolución futura, sujeto a datos etiquetados, anonimizados y evaluaciones; no es requisito para la primera versión.

## Desarrollo previsto

Definir arquitectura, modelo de eventos normalizado, reglas de detección, contratos de API y criterios de aceptación antes de implementar. Incorporar validación de archivos, límites de recursos, gestión segura de secretos, pruebas, análisis estático y CI conforme se agregue código.

## Datos y secretos

No subir logs reales, información de clientes, credenciales, archivos `.env`, cargas de usuarios ni informes generados. Los ejemplos y fixtures deberán ser sintéticos o estar anonimizados y revisados.
