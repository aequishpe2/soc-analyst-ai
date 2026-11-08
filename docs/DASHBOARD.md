# Dashboard interactivo

Disponible dentro de un análisis completado. Usar **Ver dashboard** en la cabecera para ir directamente a los gráficos. El historial permite seleccionar otra ejecución sin sobrescribir resultados.

## Visualizaciones

- Distribución por criticidad: gráfico circular y leyenda con conteos; cada categoría filtra la vista.
- Hallazgos por regla: barras seleccionables para las ocho reglas disponibles.
- Distribución diaria por fecha de inicio del hallazgo: cada día permite consultar sus hallazgos. No representa causalidad ni movimiento entre archivos. Sin fecha válida, el hallazgo se cuenta por separado.
- Usuarios y equipos con más hallazgos: hasta ocho entidades de cada tipo, ordenadas por conteo y nombre. Un clic aplica una coincidencia exacta.
- Indicadores de la vista filtrada: hallazgos, registros de evidencia únicos, grupos relacionados y hallazgos sin fecha de inicio.

Los gráficos usan agregados en la base de datos de **todos** los hallazgos coincidentes. No se calculan sobre la página visible de veinte registros. El diseño utiliza HTML y CSS sin dependencias gráficas adicionales, con botones accesibles por teclado y sus conteos como texto.

## Filtros y significado de los conteos

La API comparte las condiciones de filtrado entre `/analyses/{id}/findings` y `/analyses/{id}/dashboard`: criticidad, regla, grupo, fecha inicial/final inclusivas, usuario y equipo. No se requiere configurar una ubicación horaria. El periodo compara la fecha de **inicio** almacenada del hallazgo, no el solapamiento de todo un intervalo ni la fecha de cada evidencia.

Usuario coincide con `user` o `target_user`; equipo con `source_host` o `destination_host`. Se quitan espacios exteriores y se exige coincidencia exacta, sensible a mayúsculas. Las direcciones IP no se tratan como nombres de equipos. Si se combinan usuario y equipo, ambos deben estar presentes en el mismo evento de evidencia vinculado. Los valores ausentes o no identificables no completan los gráficos con entidades inventadas.

Cada entidad cuenta una vez por hallazgo aunque aparezca en varias filas o roles. Un hallazgo puede contener varios usuarios o equipos, de modo que sus barras no suman el total de hallazgos. Los registros de evidencia se cuentan por ID único entre todos los hallazgos filtrados. No se contabilizan como eventos nuevos las referencias compartidas.

Los indicadores superiores titulados **Totales del análisis completo**, la cobertura y la lista de grupos conservan su alcance global y se distinguen de la vista filtrada. Un grupo relacionado es un grupo con al menos un hallazgo coincidente; no es un incidente confirmado. Los filtros de visualización no cambian la configuración del motor ni los borradores de IA.

El formulario aplica periodo y entidades al pulsar **Aplicar filtros**; una línea informa los valores aplicados. Las categorías de gráficos se aplican inmediatamente y una segunda pulsación desactiva esa selección. **Restablecer filtros** elimina todas las condiciones. Las fechas de la gráfica se limitan a las últimas noventa fechas con hallazgos; si existen más, la pantalla muestra explícitamente el total y permite consultar las anteriores mediante el periodo.

## Estados y límites

Los estados de carga, error y selección vacía se muestran explícitamente. No se muestran gráficos con valores ficticios cuando faltan registros. Se rechazan periodos invertidos, reglas desconocidas y referencias a grupos de otros análisis. El frontend descarta respuestas de consultas anteriores cuando cambian los filtros.

Esta entrega añade visualización y exploración; no añade nuevas reglas, detección de anomalías, mapas geográficos ni confirmación de incidentes. El rendimiento en el máximo de 100 000 eventos y 500 000 referencias sigue pendiente de medición. El PDF y la aprobación humana auditable siguen siendo fases separadas.
