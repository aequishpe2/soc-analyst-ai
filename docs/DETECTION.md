# Motor de detección local · versión 1.1.0

## Uso

Abrir un caso y entrar en **Análisis de seguridad**. Seleccionar las importaciones ya revisadas: una revisión por archivo original, hasta 20 importaciones y 100 000 eventos en total. Confirmar el perfil de fuente, umbrales, exclusiones y calendario opcional. No se solicita configuración horaria: se usan las horas del archivo. Ejecutar y revisar hallazgos, cobertura y evidencias.

Los controles preparan un análisis nuevo. Los resultados del historial conservan su configuración, hashes y evidencias; modificar un formulario no modifica un resultado histórico. Una solicitud idéntica reutiliza el análisis previo. Un análisis fallido puede reintentarse explícitamente. Los resultados se publican únicamente al terminar la transacción completa.

El motor no usa IA, no consulta inteligencia externa, no ejecuta comandos y no realiza contención. Después del análisis, el [asistente local Qwen3](AI.md) puede preparar borradores por hallazgo sin modificar las detecciones. La revisión humana con cambios auditados sigue pendiente.

## Reglas iniciales

| Regla | Condición predeterminada | Severidad | Datos necesarios |
| --- | --- | --- | --- |
| Fallos repetidos | Al menos 10 fallos en una ventana inclusiva de 300 s, mismo origen, usuario y destino disponible | Medio | Autenticación fallida reconocida, usuario, origen válido, fecha válida |
| Posible spraying | Al menos 10 usuarios distintos con fallos desde un origen en 600 s | Alto | Autenticación fallida reconocida, usuarios, origen, fecha válida |
| Éxito después de fallos | Al menos 5 fallos estrictamente anteriores al éxito en 600 s, mismo origen, usuario y destino disponible | Alto | Autenticación y resultado reconocidos, usuario, origen, fecha válida |
| Fuera de horario | Acceso exitoso fuera del calendario confirmado | Bajo | Éxito reconocido, usuario, fecha y calendario configurado |
| Cambio de privilegios | Asignación/adición explícita, con grupo o privilegio privilegiado identificado | Medio | Acción reconocida y target_group o privilege explícito |
| Comando/proceso sospechoso | Coincidencia con patrones concretos de argumentos o nombre de herramienta | Medio | Campo command o process |
| Accesos remotos múltiples | Al menos 3 destinos distintos desde un origen para un usuario en 600 s | Alto | Autenticación remota exitosa reconocida, usuario, origen y destino distintos, fecha válida |
| Alteración de controles | Tipo explícito de desactivación/borrado o Windows Security 1102 | Alto | Semántica reconocida; no se infiere de ausencia de logs |

Los umbrales y ventanas se configuran y quedan versionados. Un origen puede ser IP válida o equipo de origen explícito; un destino puede ser equipo o IP válida. No se asume que una columna ambigua llamada Host represente el origen: revisar el mapeo. Sin destino, los fallos y éxitos se agrupan por usuario/origen; no se puede atribuir con certeza el servicio afectado.

Direcciones sin especificar (0.0.0.0 y ::), multicast o broadcast global no se usan como identidad de origen/destino. Los identificadores vacíos y marcadores como -, N/A, null o unknown tampoco se interpretan como usuarios/equipos conocidos.

Las ventanas solapadas que cumplen fuerza bruta/spraying/accesos remotos se agrupan en una secuencia. El hallazgo distingue **máximo dentro de una ventana** y **total de referencias de la secuencia**; no afirma que toda una secuencia prolongada ocurrió en cinco minutos. Un éxito reinicia la secuencia de fallos de su clave. Fallos con la misma hora que el éxito no se presentan como anteriores.

## Semántica de los eventos

El perfil genérico usa valores explícitos, sin buscar palabras arbitrarias dentro del mensaje. Los tipos se pasan a minúsculas y se sustituyen espacios/guiones por guiones bajos para compararlos. La lista efectiva también está en `GET /api/v1/detection/rules`.

- Autenticación: login, logon, authentication, auth, user_login, inicio_sesion; además login_failed, login_failure, failed_login, failed_logon, authentication_failure, auth_fail, login_success, authentication_success, successful_logon y auth_success.
- Accesos remotos: remote_login, remote_logon, ssh_login, rdp_login, smb_login y winrm_login. Un login genérico no se interpreta como remoto.
- Éxito: success, successful, succeeded, exito, éxito, ok, allowed, permitido. Fallo: failure, failed, fail, denied, denegado, error. No se deduce el significado de 0, 1, true o false. Los tipos que declaran éxito/fallo ya aportan ese resultado; una contradicción con un resultado reconocido excluye el evento de reglas semánticas.
- Asignación: privileged_group_member_added, group_member_added, privileged_role_assigned, privilege_elevated y privilege_escalation. El tipo por sí solo no basta: hace falta un destino privilegiado explícito.
- Controles: audit_log_cleared, security_log_cleared, security_control_disabled, edr_disabled y audit_disabled.

Otros valores quedan fuera de las reglas que no pueden interpretarlos y aparecen en cobertura. No hay traducción universal de formatos SIEM. Los adaptadores adicionales y las equivalencias configurables de valores serán una evolución posterior.

Para códigos Windows se exige el proveedor mapeado `Microsoft-Windows-Security-Auditing` o que el analista confirme el perfil Windows Security para todas las fuentes seleccionadas. No se interpreta un número de evento aislado como Windows:

- 4624: éxito; 4625: fallo. Para accesos remotos, además LogonType 3 o 10. Tipo 3 también puede corresponder a servicios o administración legítima.
- 4728, 4732 y 4756: adición de miembro a un grupo; solo genera hallazgo de privilegios si el destino está identificado como privilegiado.
- 1102: borrado del registro de seguridad.
- 4672 y 4719 se reconocen sin usarlos como prueba de escalamiento o de desactivación: privilegios especiales al iniciar sesión y cambio de política no demuestran esas conclusiones por sí solos.

Grupos privilegiados: nombres exactos configurados (comparación sin distinguir mayúsculas), SID S-1-5-32-544 y SID de dominio con RID 512/518/519. El nombre parcial Non-Administrators no coincide con Administrators. Para privilege, se admiten los roles explícitos root, administrator, admin, system o sudo; no se considera que una cuenta llamada root demuestre una elevación. La nueva normalización versión 3 admite proveedor, tipo de logon, grupo, cuenta afectada y privilegio. Importaciones anteriores pueden requerir una nueva revisión de mapeo para aportar estos campos.

## Patrones de comandos

Se inspeccionan tokens como datos, sin ejecutar ni decodificar contenido. Catálogo acotado: PowerShell/pwsh con -enc o -EncodedCommand y argumento; procdump con -ma y objetivo lsass; wevtutil cl/clear-log Security/System; auditctl -e 0; nombre/invocación mimikatz. No se marca PowerShell por existir ni se busca una invocación incrustada dentro de echo. Los argumentos posteriores a -Command o -File no se interpretan como parámetros del lanzador PowerShell.

Una cadena registrada no demuestra ejecución exitosa ni intención maliciosa. No se interpretan todas las construcciones de shell, alias, comandos anidados, ofuscación o variantes de herramientas. La ausencia de coincidencia no certifica que un comando sea seguro.

## Evidencia, riesgo y cobertura

Cada hallazgo tiene regla y versión, severidad, confianza, criterio observado, intervalo cuando existe, limitaciones, impacto **potencial**, acciones propuestas y referencias a eventos dentro del alcance. Las referencias enlazan archivo, hash, hoja, fila, configuración y valores originales. Ninguna recomendación se presenta como ejecutada.

Crítico está reservado para una evaluación de impacto grave/activos críticos que esta versión aún no realiza; no se asigna automáticamente. La confianza es la confianza en la inferencia de riesgo (Baja/Media), no una probabilidad calibrada ni una confirmación de compromiso. Las referencias ATT&CK son orientativas para investigación, no atribución de técnicas confirmadas.

Cobertura distingue Evaluada, Parcial, No evaluable y No aplicable; cuenta eventos elegibles y razones de descarte (semántica desconocida, contradicción, campo ausente, calendario no configurado, etc.). Las filas rechazadas al importar se muestran por separado. Los eventos sin hora válida se excluyen de las reglas temporales, pero pueden aportar evidencia directa de un comando o un tipo explícito de acción.

No se aplican listas de cuentas administrativas legítimas automáticamente. Las exclusiones por usuario exacto o IP de origen se registran, afectan a todas las reglas y se cuentan en el resumen. Los nombres de usuario se comparan de forma exacta tras quitar espacios extremos; no se resuelven dominios, alias ni identidades homónimas.

## Duplicados y correlación

No se admite combinar dos revisiones/lecturas del mismo hash original. Entre archivos distintos, registros con todos los campos normalizados equivalentes y la misma referencia temporal comparable se cuentan una vez para no inflar umbrales. Se conserva cada registro original y se puede consultar la relación copia/representante. Las horas sin referencia solo se deduplican dentro de su importación, y las fechas inválidas conservan el valor crudo para comparar. La política puede subcontar eventos legítimos indistinguibles cuando faltan identificadores o precisión temporal; exportaciones parcialmente distintas también pueden ocultar duplicados no identificables.

La correlación produce un bosque de vínculos verificables: evidencia compartida, o usuario y activo coincidentes. Una IP sola no une hallazgos. Los vínculos por entidad deben respetar un intervalo global de hasta 1800 s, configurable, evitando cadenas ilimitadas. Los vínculos por el mismo evento pueden conectar secuencias largas que comparten esa evidencia. Los grupos no son incidentes confirmados ni necesariamente una partición correcta de incidentes reales.

## Persistencia y límites

Un análisis guarda alcance, configuración, reglas/motor e input_hash SHA-256 de entradas, configuración y procedencia. Las fuentes originales se verifican antes de ejecutar. Las importaciones son instantáneas y los resultados históricos no se sobrescriben. Se persisten resultados y estado completado en una sola transacción; un fallo revierte grupos, hallazgos y evidencias. Al reiniciar, los análisis pendientes se marcan interrumpidos y pueden reintentarse.

Las fechas sin referencia no se convierten inventando una ubicación: sus ventanas y relaciones temporales se limitan al reloj del archivo. Las fechas con referencia explícita sí permiten correlación entre archivos. El calendario se aplica a la hora registrada; para valores Unix sin hora local explícita, esa regla queda no evaluable. Los análisis históricos permanecen intactos; no se reejecutan con criterios nuevos bajo una versión antigua.

Límites: 100 000 eventos, 20 importaciones, 64 MiB de entrada normalizada serializada, 5000 hallazgos y 500 000 referencias. Los excesos fallan explícitamente sin resultados parciales. Comparte la cola local de la importación y requiere una sola instancia de API; el cálculo corre fuera del bucle HTTP. No hay sandbox ni límite de RAM/tiempo de SO para el cálculo analítico. PostgreSQL/Compose y rendimiento máximo siguen pendientes de validación. Autenticación y autorización multiusuario continúan pendientes: mantener localhost.

## API

Todo bajo `/api/v1`: `GET /cases/{id}/imports` para seleccionar revisiones; `POST /cases/{id}/analyses` con import_ids y settings; `GET /cases/{id}/analyses` para historial; `GET /analyses/{id}` para estado/configuración/cobertura; `POST /analyses/{id}/retry` para fallidos. El propio análisis tiene estado durable, separado de los jobs de importación.

Resultados completos: `GET /analyses/{id}/findings` (filtros severity, rule_id, group_id); `GET /analyses/{id}/findings/{finding_id}/evidence`; `GET /analyses/{id}/groups`; `GET /analyses/{id}/duplicates`. Listados con offset/limit (máximo 100). Recursos fuera del alcance se rechazan; esto comprueba pertenencia, no sustituye autorización por usuario.

## Fuentes de semántica

- [Microsoft: evento 4672 y su contexto](https://learn.microsoft.com/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4672).
- [Microsoft: accesos, grupos y auditoría en SecurityEvent](https://github.com/MicrosoftDocs/azure-monitor-docs/blob/main/articles/azure-monitor/reference/queries/securityevent.md).
- [Microsoft: diferenciar 1102 y 4719](https://learn.microsoft.com/azure/azure-monitor/reference/queries/windowsevent).
- [MITRE ATT&CK: fuerza bruta y subtipos](https://attack.mitre.org/techniques/T1110/).
