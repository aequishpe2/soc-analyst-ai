# SOC Analyst AI

Aplicación web planificada para apoyar a analistas SOC Nivel 2 en el análisis de registros exportados de un SIEM en Excel (.xlsx) y CSV, sin integración directa con el SIEM.

## Estado

Arquitectura y plan de desarrollo documentados. La aplicación todavía no está implementada.

## Documentación

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
