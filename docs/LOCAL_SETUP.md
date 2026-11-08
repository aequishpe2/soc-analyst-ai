# Desarrollo local

Esta fase permite crear/listar casos, importar Excel/CSV y ejecutar reglas de seguridad con evidencias y cobertura. No utiliza el agente de IA ni genera informes todavía. Consultar [la guía de importación](INGESTION.md) y [el motor de detección](DETECTION.md). No tiene autenticación: usar exclusivamente en un equipo de confianza, con puertos ligados a loopback; no publicar ni compartir por túneles.

## Este equipo: inicio directo en Windows

Los runtimes Node 24, Python 3.12 y Ollama se prepararon de forma local en `.tools/` y `.venv/`. No necesitan agregarse al PATH ni requieren Docker para usar esta fase. Estos binarios no se suben a GitHub; otro equipo debe instalar sus propios runtimes siguiendo las opciones de abajo.

- Abrir `Iniciar-SOC.cmd` desde la raíz para iniciar Ollama, API e interfaz.
- Visitar http://127.0.0.1:3000 en el navegador.
- Abrir `Detener-SOC.cmd` para detener los procesos registrados, conservando datos y modelo.

También se pueden ejecutar `powershell -File scripts/Start-Local.ps1 -WithAI` y `powershell -File scripts/Stop-Local.ps1`. Los scripts no cambian la política de ejecución de Windows; si una política corporativa los bloquea, debe resolverlo el administrador. No iniciar una segunda sesión cuando los servicios ya estén activos.

En este equipo se autorizó RemoteSigned únicamente para el usuario actual de Windows PowerShell, porque su configuración inicial bloqueaba todos los scripts. Los scripts del proyecto no alteran esta preferencia durante el arranque.

La base persistente es `.local/soc.db`; los modelos están en `.local/models/` y los logs de los servicios en `.local/`. El registro de procesos valida ejecutable y fecha de inicio antes de detener un proceso. No borres ni edites ese registro mientras los servicios estén activos. Si el inicio falla, revisa los logs y ejecuta el comando de detener antes de reintentar. Los datos de prueba de la entrega anterior están en una base separada.

La primera descarga del modelo se hace con el servidor iniciado:

```powershell
.tools/ollama/ollama.exe pull qwen3:8b
```

No hace falta repetirla en cada arranque. Tras la descarga, recargar la interfaz para ver «Modelo disponible». Esta indicación verifica instalación, no habilita todavía el análisis de evidencias. Los procesos iniciados con estos scripts continúan en segundo plano; usar el comando de detener cuando termines.

Para comprobar la web, la API y una respuesta real del modelo con un mensaje sintético:

```powershell
powershell -File scripts/Test-Local.ps1 -WithAI
```

La comprobación puede tardar varios minutos en CPU. Guarda métricas básicas en `.local/ai-smoke.json` y descarga el modelo de la memoria al terminar. No envía registros de clientes ni demuestra todavía la calidad del análisis SOC.

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

Crear un caso, abrirlo y cargar un archivo sintético. Revisar la vista previa, el mapeo y el formato de fecha antes de confirmar. Comprobar que los conteos cuadran y abrir un evento para ver su hoja/fila original y hash. Con Ollama apagado, los casos y la importación deben seguir funcionando. Los listados están paginados. La aplicación sí conserva los archivos y eventos importados: requieren protección y no deben subirse al repositorio.

## Límites de esta entrega

Desde un caso, entrar en Análisis de seguridad, seleccionar revisiones y confirmar el contexto. Sin un calendario configurado, la regla de horario queda No evaluable. Si no hay campos de grupo/rol o tipo de acceso remoto, la cobertura debe indicar esas limitaciones; volver a importar con el mapeo apropiado si existen esas columnas en la fuente. No elegir Windows Security para códigos numéricos de otros proveedores.

La cola es local y admite una sola instancia de API; Celery/Redis, revisión humana auditable, gráficos, agente de IA, PDF y OIDC están pendientes. No hay validación de despliegue compartido. Los tags de imágenes se fijan por versión principal o release; antes de producción se deberán fijar también digests y revisar su procedencia. La IA local reduce transmisión externa; no sustituye cifrado, control de acceso o seguridad del equipo.

Fuentes: [Ollama: desactivar cloud](https://docs.ollama.com/faq), [Next.js: instalación](https://nextjs.org/docs/app/getting-started/installation).

La creación de casos, la carga y el análisis no solicitan configuración horaria. Se utilizan las fechas del archivo automáticamente.
