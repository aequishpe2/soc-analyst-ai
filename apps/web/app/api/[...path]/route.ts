import { NextRequest, NextResponse } from "next/server";

const uuid =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const reads = new RegExp(
  `^v1/(?:system|detection/rules|cases|cases/${uuid}|cases/${uuid}/(?:files|events|imports|analyses)|cases/${uuid}/events/${uuid}|files/${uuid}/(?:preview|jobs|imports)|jobs/${uuid}|imports/${uuid}/issues|analyses/${uuid}|analyses/${uuid}/(?:findings|groups|duplicates)|analyses/${uuid}/findings/${uuid}/(?:evidence|draft))$`,
);
const writes = new RegExp(
  `^v1/(?:cases|cases/${uuid}/(?:files|analyses)|files/${uuid}/imports|jobs/${uuid}/retry|analyses/${uuid}/retry|analyses/${uuid}/findings/${uuid}/draft)$`,
);
const uploadPath = new RegExp(`^v1/cases/${uuid}/files$`);

async function readBounded(request: NextRequest, limit: number) {
  if (Number(request.headers.get("content-length")) > limit)
    throw new RangeError();
  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > limit) {
          await reader.cancel();
          throw new RangeError();
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result.buffer;
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = path.join("/");
  const post = request.method === "POST";
  const headers = { "Cache-Control": "no-store" };
  if (!(post ? writes : reads).test(route))
    return NextResponse.json(
      { message: "Ruta no disponible" },
      { status: 404, headers },
    );
  if (post) {
    const host = request.headers.get("host");
    const origin = request.headers.get("origin");
    const allowed =
      host && /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)
        ? [`http://${host}`, `https://${host}`]
        : [];
    if (!origin || !allowed.includes(origin))
      return NextResponse.json(
        { message: "Origen no permitido" },
        { status: 403, headers },
      );
  }
  try {
    const upload = post && uploadPath.test(route);
    const contentType =
      request.headers.get("content-type") ?? "application/json";
    if (upload && !contentType.startsWith("multipart/form-data;"))
      return NextResponse.json(
        { message: "Carga multipart requerida" },
        { status: 415, headers },
      );
    const body = post
      ? await readBounded(request, upload ? 20 * 1024 * 1024 + 65536 : 65536)
      : undefined;
    const response = await fetch(
      `${process.env.API_URL ?? "http://127.0.0.1:8000"}/api/${route}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: { "Content-Type": contentType },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(30000),
      },
    );
    const text = await response.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = {
        message:
          response.status === 413
            ? "La carga supera el límite de tamaño."
            : "La API no pudo procesar la solicitud.",
      };
    }
    return NextResponse.json(data, { status: response.status, headers });
  } catch (error) {
    return NextResponse.json(
      {
        message:
          error instanceof RangeError
            ? "La solicitud supera el límite de tamaño."
            : "No se pudo conectar con la API local. Recarga para consultar si el trabajo quedó registrado.",
      },
      { status: error instanceof RangeError ? 413 : 503, headers },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
