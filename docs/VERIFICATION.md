# Verificación de la base local

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
