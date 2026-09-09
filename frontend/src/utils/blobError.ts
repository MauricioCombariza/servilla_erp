export async function extraerErrorBlob(e: unknown): Promise<string> {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text());
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch {
      // no era JSON, cae al mensaje genérico
    }
  }
  return "Error al generar el reporte";
}
