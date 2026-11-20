/**
 * Última actividad de la persona (teclado, toques, lecturas de pistola, envíos).
 * Se guarda también en localStorage para que todas las pestañas del ERP la compartan:
 * trabajar en una mantiene viva la sesión en las otras.
 */
const CLAVE = "servilla-ultima-actividad";
let ultima = Date.now();
let escrita = 0;

export function marcarActividad(): void {
  ultima = Date.now();
  // Una escritura cada 5 s basta (mover el mouse dispara cientos de eventos)
  if (ultima - escrita < 5_000) return;
  escrita = ultima;
  try {
    localStorage.setItem(CLAVE, String(ultima));
  } catch {
    // modo privado o almacenamiento bloqueado: vale la de esta pestaña
  }
}

export function ultimaActividad(): number {
  try {
    const otra = Number(localStorage.getItem(CLAVE) ?? 0);
    if (otra > ultima) ultima = otra;
  } catch {
    // sin almacenamiento: solo esta pestaña
  }
  return ultima;
}
