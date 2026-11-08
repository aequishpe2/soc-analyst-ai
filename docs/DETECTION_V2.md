# Motor contextual 2.0

Versión activa: motor `2.0.0`, catálogo `soc-context-1`, normalizador `4`, flujo `automatic-2` y composición IA `grounded-outline-2`. El catálogo contiene **19 reglas**. Los resultados de versiones anteriores se conservan y se identifican como históricos; no se recalculan silenciosamente.

## Interpretación de los registros

El perfil predeterminado es automático por registro. Se separan proveedor, canal, descripción y equipo que registra el evento. `Hostname` no se convierte en origen de red: alimenta `reporting_host`. `Log_Source` alimenta `event_channel`, y `Event_Description` se conserva como descripción, sin convertir prosa arbitraria en un tipo de evento.

Fuentes y formatos admitidos en esta versión:

| Fuente | Interpretación |
| --- | --- |
| Windows Security | Autenticación, sesión privilegiada, procesos, cuentas, cambios de grupo, recursos compartidos, archivos, red, tareas y auditoría mediante IDs expresamente catalogados |
| Windows System | Instalación de servicio 7045 y estado 7036; no se deduce instalación de un simple estado de servicio |
| PowerShell | 4104 en canal PowerShell; extracción del prefijo exacto de bloque de script del formato admitido |
| Proxy exportado | `PROXY_ACCESS` con canal Proxy; claves explícitas `bytes_out`, `method`, `status`; descripción exacta de POST del formato conocido |
| IIS exportado | `HTTP_ACCESS` con canal IIS; URL y parámetros analizados como datos, sin ejecutar ni visitar el destino |
| Firewall exportado | 5156 con canal Firewall se reconoce como actividad de red; no implica por sí solo una alerta |
| Tipos canónicos | Las etiquetas explícitas ya admitidas siguen disponibles para CSV genéricos |

Los IDs numéricos solos no identifican al proveedor. La inferencia por canal es una interpretación del formato aportado, no una certificación de procedencia. Las descripciones solo alimentan campos derivados delimitados, por ejemplo `LogonType=10`; se guarda campo origen y método de extracción. Valores contradictorios se excluyen. No se usa texto libre como instrucciones.

El resumen distingue eventos con tipo interpretado, eventos desconocidos, fuentes y clases de actividad. Un evento interpretado puede ser normal y no equivale a una detección. La cobertura muestra elegibles, descartes y límites por regla; las reglas que no tienen el contexto requerido permanecen no evaluables.

## Reglas

| Regla | Condición principal | Prioridad |
| --- | --- | --- |
| Fallos repetidos | Diez fallos en 300 s con mismo origen, usuario y destino disponible | Medio |
| Posible spraying | Diez usuarios distintos con fallos desde un origen en 600 s | Alto |
| Éxito tras fallos | Éxito tras cinco fallos estrictamente anteriores, mismas entidades, 600 s | Alto |
| Fuera de horario | Éxito fuera del calendario explícitamente configurado | Bajo |
| Cambio de privilegios | Asignación explícita a un grupo/privilegio privilegiado identificable | Medio |
| Comando sospechoso | Patrones ya admitidos de PowerShell codificado, credenciales y auditoría | Medio |
| Abanico remoto | Tres destinos distintos con acceso remoto exitoso en 600 s | Alto |
| Alteración de controles | Desactivación/borrado explícito, con semántica de proveedor válida | Alto |
| Ráfaga distribuida | Veinte fallos en 900 s desde un origen y al menos dos combinaciones cuenta/destino | Alto |
| Éxito remoto tras fallos | Al menos tres fallos y éxito remoto posterior, mismo origen/cuenta/equipo, 600 s | Alto |
| Sesión privilegiada | 4672 relacionado por cuenta/equipo/tiempo con un inicio exitoso previo | Medio |
| Tarea programada | 4698/4702 o etiqueta canónica; se inspecciona la acción disponible | Medio; Alto si usa un intérprete de scripts o ruta no propia del sistema |
| Servicio instalado | 7045/System o 4697/Security; se inspecciona la ruta disponible | Medio; Alto para binario bajo ProgramData, Users Public o Temp |
| Recuperación inhibida | Orden explícita de eliminar copias o desactivar recuperación | Alto; Crítico bajo la condición específica descrita abajo |
| Archivo comprimido | Operación concreta de creación con 7z o tar | Bajo |
| Transferencia POST | Más de 100 MiB registrados en una ventana de 900 s con mismas entidades disponibles | Alto |
| Comando en solicitud web | Endpoint de script con parámetro `cmd`, `exec` o `command` y una orden del sistema admitida | Alto |
| Enumeración | Órdenes concretas net view/group/localgroup o enumeración PowerShell admitida | Bajo |
| Secuencia remota y compartida | Acceso a recurso compartido posterior a autenticación remota, misma cuenta y equipo | Medio |

Los umbrales de ráfagas, ventanas y volumen se conservan en la configuración y pueden ajustarse. Las ventanas son inclusivas; los fallos de una secuencia de éxito deben ser estrictamente anteriores. Las horas sin referencia solo se relacionan dentro de su importación. Los eventos indistinguibles no multiplican los umbrales y sus copias siguen conservadas.

## Política de prioridad

La criticidad expresa **prioridad de investigación**, no probabilidad de compromiso ni impacto confirmado. Se conserva confianza, justificación, factores, reglas, evidencias y limitaciones por separado.

- Bajo, 25/100: actividad observable con explicaciones administrativas habituales, como compresión o enumeración.
- Medio, 50/100: condición que requiere contexto adicional, por ejemplo una sesión privilegiada o una tarea sin otros indicadores.
- Alto, 75/100: patrón o secuencia de mayor riesgo, como éxito remoto tras fallos, volumen POST elevado o persistencia en una ruta no propia del sistema.
- Crítico, 95/100: en esta versión, la condición concreta `vssadmin delete shadows /all /quiet` en un registro de proceso cuyo resultado figura como exitoso. La prioridad proviene de la orden total y silenciosa contra la recuperación; **el éxito del evento de proceso no demuestra que las copias se hayan borrado**. Una orden fallida o sin esas condiciones permanece Alta.

Los valores son categorías discretas de política, no puntuaciones probabilísticas calibradas. No se copian del campo Severity del Excel. Un Crítico no confirma ransomware y los accesos privilegiados no se convierten en escalamiento por el solo hecho de tener ID 4672.

## Evidencias y límites de las relaciones

Cada hallazgo enlaza filas, hoja, archivo y hash. Las derivaciones identifican el origen y el método. La correlación por cuenta, equipo y tiempo es una relación para investigar; sin ID de sesión no permite asegurar que dos eventos pertenezcan a la misma sesión. No se mezclan relojes de archivos no comparables ni se unen grupos por una IP sola.

Una tarea, servicio o archivo comprimido puede estar autorizado. Un POST grande no identifica el contenido ni prueba exfiltración. Una petición con comando no demuestra ejecución en el servidor ni una web shell implantada. Estos límites aparecen en los hallazgos y en las explicaciones de IA.

El soporte de Proxy/IIS corresponde al formato exportado descrito, no a todos los productos o versiones de SIEM. No se han implementado reputación de IP, geolocalización, modelos de anomalías con baseline, todos los patrones de explotación, ni verificación de impacto sobre los activos. La ausencia de una alerta no descarta esas actividades.

## Versionado y validación

La migración 0007 permite una ejecución automática por archivo **y versión**, de modo que cargar de nuevo o reanalizar con el motor actual no recupera sin aviso un resultado viejo. La UI señala el motor histórico y permite solicitar una nueva revisión en casos de una fuente.

Las pruebas incluyen positivos y negativos, contradicciones, resultados fallidos, comandos citados como texto, consultas web normales, volumen POST frente a GET, proveedor/canal incorrectos, fechas no comparables y conservación de versiones. Son verificaciones funcionales sobre fixtures sintéticos; no acreditan precisión o recobrado universal en producción.

Referencias primarias: [MITRE T1490, recuperación](https://attack.mitre.org/techniques/T1490/), [Microsoft 4672](https://learn.microsoft.com/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4672), [Microsoft 4698](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4698), [Microsoft: catálogo de eventos](https://learn.microsoft.com/en-au/windows-server/identity/ad-ds/plan/appendix-l--events-to-monitor).
