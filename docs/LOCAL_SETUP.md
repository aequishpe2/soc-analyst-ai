# Desarrollo local

Esta fase permite crear/listar casos y consultar disponibilidad de Ollama. No importa logs, no ejecuta análisis ni genera informes todavía. No tiene autenticación: usar exclusivamente en un equipo de confianza, con puertos ligados a loopback; no publicar ni compartir por túneles.

## Opción recomendada: Docker Desktop

Instalar Docker Desktop desde su fuente oficial y habilitar su motor Linux. Desde la raíz:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Abrir http://localhost:3000. Contrato OpenAPI: http://localhost:8000/docs. La API espera a PostgreSQL y aplica migraciones antes de aceptar solicitudes. Los datos sobreviven a `docker compose down` en el volumen de PostgreSQL. La contraseña de ejemplo es solo para desarrollo; no usar con datos de clientes.

## Activar IA local opcional

```powershell
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull qwen3:8b
```

La descarga requiere Internet y varios GB; las consultas posteriores al modelo se ejecutan localmente. El contenedor desactiva las funciones cloud mediante `OLLAMA_NO_CLOUD=1`; no publica su puerto en el host. Perfil CPU inicial: no presupone GPU dedicada ni aceleración de la NPU Intel. La interfaz consulta disponibilidad al abrirla; recargar después de descargar el modelo. Esta fase solo comprueba disponibilidad, todavía no envía evidencias al modelo.

## Sin Docker (desarrollo)

Requiere Node.js 24, uv y Python 3.12. En una terminal desde `apps/api`:

```powershell
uv sync --frozen --python 3.12
$env:DATABASE_URL='sqlite:///local.db'
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

SQLite es una alternativa para verificar esta primera fase; Compose utiliza PostgreSQL. Mantener DATABASE_URL configurada en cada terminal que acceda a esa base. No se crean tablas automáticamente durante el arranque HTTP. Sin DATABASE_URL, la API usa SQLite efímero y readiness falla hasta disponer de un esquema persistente.

En otra terminal desde `apps/web`:

```powershell
npm ci
npm run dev
```

La interfaz usa su proxy interno hacia `http://127.0.0.1:8000`; no necesita exponer credenciales al navegador. Para Ollama nativo, iniciar el servidor con `OLLAMA_NO_CLOUD=1`, descargar `qwen3:8b` y mantener el servicio en 127.0.0.1:11434. El endpoint de diagnóstico usa una lista cerrada de destinos locales y no admite modelos cloud.

## Comprobaciones

```powershell
# apps/api
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pip-audit
# apps/web
npm run typecheck
npm run build
npm audit --omit=dev --audit-level=high
```

Crear un caso, recargar y comprobar su persistencia. Con Ollama apagado, crear/listar casos debe seguir funcionando. Una zona IANA inválida se rechaza. Los casos de esta fase no almacenan datos de clientes ni evidencias. El listado está paginado a 20 elementos.

## Límites de esta entrega

El worker, la carga segura, las reglas, la revisión IA, la exportación PDF y OIDC están pendientes. No hay validación de despliegue compartido. Los tags de imágenes se fijan por versión principal o release; antes de producción se deberán fijar también digests y revisar su procedencia. La IA local reduce transmisión externa; no sustituye cifrado, control de acceso o seguridad del equipo.

Fuentes: [Ollama: desactivar cloud](https://docs.ollama.com/faq), [Next.js: instalación](https://nextjs.org/docs/app/getting-started/installation).
