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

Pendiente de verificar: Docker Compose, PostgreSQL real, descarga/inferencia de Qwen3, aceleración de hardware y ejecución remota de GitHub Actions. No están instalados Docker ni Ollama en este entorno. Las pruebas usan SQLite; no sustituyen una integración con PostgreSQL. Starlette emite un aviso de deprecación sobre su integración de pruebas con httpx; las pruebas pasan y la API usa httpx únicamente para el diagnóstico local de Ollama.

La infraestructura incluye CI para comprobaciones y escaneo de secretos. Su configuración en el repositorio no equivale a una ejecución remota aprobada.
