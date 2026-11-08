# Matriz MITRE ATT&CK

El dashboard incluye la matriz Enterprise. El menú **MITRE ATT&CK** lleva a sus columnas: cada celda muestra identificador, nombre oficial, número de hallazgos y prioridad máxima entre ellos. Pulsar una técnica filtra la lista y los gráficos; **Investigar hallazgo** permite abrir las evidencias originales. Pulsar de nuevo o **Quitar filtro MITRE** restaura la selección.

La matriz respeta los otros filtros y mantiene las columnas al seleccionar una técnica. Restablecer filtros, cambiar de análisis o elegir otro grupo elimina la selección MITRE. Las columnas se desplazan horizontalmente dentro de la matriz y pueden recorrerse con teclado. Los enlaces abren la referencia oficial.

## Catálogo y significado

Se incluye un subconjunto local del catálogo oficial **Enterprise 20.1**, con sus 15 tácticas y las 16 referencias utilizadas por el motor, incluida una retirada. Identificadores, nombres, pertenencia a tácticas y estado proceden de los datos STIX de MITRE. Las tácticas se presentan también en español. La aplicación no necesita conexión para generar la matriz.

- [Matriz oficial Enterprise](https://attack.mitre.org/matrices/enterprise/).
- [Datos STIX oficiales 20.1](https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-20.1.json).
- [Repositorio y condiciones de uso de MITRE](https://github.com/mitre-attack/attack-stix-data).

Son referencias **contextuales**, no técnicas confirmadas. Un POST voluminoso no prueba un canal de mando y control, una petición con comandos no demuestra una web shell, y una sesión privilegiada no demuestra abuso de cuentas. La matriz no aumenta la criticidad ni cambia los hallazgos.

Una técnica puede pertenecer a varias tácticas: aparece en cada columna correspondiente, pero los totales de hallazgos y técnicas se calculan una vez. Las columnas no demuestran fases ejecutadas ni una cadena de ataque; sus conteos no se suman como incidentes ni constituyen un porcentaje de cobertura de ATT&CK. Una columna vacía no demuestra ausencia de actividad.

Las referencias sin asignar, desconocidas o retiradas se cuentan por separado. En 20.1, `T1562` está retirada: los análisis que la contienen conservan ese dato, sin asignarle otra técnica automáticamente. No se alteran las importaciones, evidencias ni versiones históricas del motor.

## API, filtros y PDF

- `GET /api/v1/analyses/{id}/attack-matrix`: agregación completa, sin paginación; acepta los mismos filtros de los hallazgos. Devuelve catálogo, técnicas, columnas, conteos únicos y motivos de referencias no activas.
- `technique_id`: filtro validado adicional para hallazgos, dashboard y matriz. Coincide con la referencia conservada y se combina con criticidad, regla, grupo, fechas, usuario y equipo.
- El proxy permite la nueva ruta de lectura y conserva sus restricciones.
- La instantánea del informe incluye la matriz y la versión del catálogo. Su huella cambia con ese contenido; una vista previa antigua debe actualizarse antes de descargar.
- Ambos PDF incluyen una tabla compacta de técnica, tácticas y etiquetas de hallazgos. Estas etiquetas enlazan conceptualmente con el detalle y sus referencias de evidencia. El caso local conserva seis páginas en el PDF para cliente.

## Mantenimiento y verificación

`scripts/build_attack_catalog.py` genera el subconjunto desde una versión fijada de los datos oficiales. Guarda URL, versión y SHA-256 del bundle. Requiere red solo al actualizarlo; los cambios de versión, traducciones y referencias deben revisarse antes de publicar. En ejecución se usa `app/data/attack-enterprise.json`.

Las pruebas comprueban referencias del motor incluidas en el catálogo, matrices vacías, técnicas con varias tácticas sin duplicar totales, prioridad máxima, referencias desconocidas/retiradas, filtros, aislamiento entre casos, acceso a evidencias, estado del análisis, agregación sin paginación y referencias en el PDF.

MITRE ATT&CK® y ATT&CK® son marcas de The MITRE Corporation. Los identificadores y nombres oficiales se atribuyen a MITRE; la aplicación añade su presentación y relación con hallazgos locales.
