import { NextRequest, NextResponse } from "next/server";

// Explicit routes only: this is not a general-purpose HTTP proxy.
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = path.join("/");
  if (
    !["v1/cases", "v1/system"].includes(route) ||
    (request.method === "POST" && route !== "v1/cases")
  ) {
    return NextResponse.json(
      { message: "Ruta no disponible" },
      { status: 404 },
    );
  }
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    const host = request.headers.get("host");
    const allowedOrigins =
      host && /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)
        ? [`http://${host}`, `https://${host}`]
        : [];
    if (!origin || !allowedOrigins.includes(origin)) {
      return NextResponse.json(
        { message: "Origen no permitido" },
        { status: 403 },
      );
    }
  }
  try {
    const body = request.method === "POST" ? await request.text() : undefined;
    if (body && Buffer.byteLength(body) > 4096) {
      return NextResponse.json(
        { message: "Solicitud demasiado grande" },
        { status: 413 },
      );
    }
    const response = await fetch(
      `${process.env.API_URL ?? "http://127.0.0.1:8000"}/api/${route}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(6000),
      },
    );
    return NextResponse.json(await response.json(), {
      status: response.status,
    });
  } catch {
    return NextResponse.json(
      { message: "No se pudo conectar con la API local." },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
