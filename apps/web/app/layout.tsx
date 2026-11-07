import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "SOC Analyst AI | Investigaciones",
  description: "Espacio local de investigación y análisis de evidencias SIEM",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
