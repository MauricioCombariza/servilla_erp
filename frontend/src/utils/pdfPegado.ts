import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

interface FilaPegado {
  fecha: string;
  personal_nombre: string;
  cantidad: number;
  tarifa_unitaria: number;
  total: number;
}

const fmtCop = (v: number) =>
  new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(v);

const fmtNum = (v: number) =>
  new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(v);

export function generarPdfPegado(filas: FilaPegado[], periodo: string): void {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "letter" });

  // ── Encabezado ────────────────────────────────────────────────────────────
  doc.setFontSize(14);
  doc.setFont("helvetica", "bold");
  doc.text("Planilla de Pegado de Guías", 105, 18, { align: "center" });
  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.text(`Período: ${periodo}`, 105, 25, { align: "center" });
  doc.text(`Generado: ${new Date().toLocaleDateString("es-CO")}`, 105, 31, { align: "center" });

  // ── Agrupar por persona (sumar todo el mes) ───────────────────────────────
  const porPersona = new Map<string, { cantidad: number; tarifa: number; total: number }>();
  for (const f of filas) {
    const prev = porPersona.get(f.personal_nombre);
    if (prev) {
      prev.cantidad += f.cantidad;
      prev.total += f.total;
    } else {
      porPersona.set(f.personal_nombre, {
        cantidad: f.cantidad,
        tarifa: f.tarifa_unitaria,
        total: f.total,
      });
    }
  }

  const rows = [...porPersona.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const totalGuias = rows.reduce((s, [, v]) => s + v.cantidad, 0);
  const totalValor = rows.reduce((s, [, v]) => s + v.total, 0);
  const tarifaRef = rows[0]?.[1].tarifa ?? 0;

  autoTable(doc, {
    startY: 38,
    head: [["Personal", "Guías pegadas", "Tarifa / guía", "Total"]],
    body: rows.map(([nombre, v]) => [
      nombre,
      fmtNum(v.cantidad),
      fmtCop(v.tarifa),
      fmtCop(v.total),
    ]),
    foot: [[
      { content: "TOTAL MES", styles: { fontStyle: "bold" } },
      { content: fmtNum(totalGuias), styles: { fontStyle: "bold" } },
      { content: fmtCop(tarifaRef), styles: { fontStyle: "bold" } },
      { content: fmtCop(totalValor), styles: { fontStyle: "bold" } },
    ]],
    theme: "striped",
    headStyles: { fillColor: [63, 81, 181], fontSize: 10, fontStyle: "bold" },
    footStyles: { fillColor: [63, 81, 181], textColor: [255, 255, 255], fontSize: 10, fontStyle: "bold" },
    bodyStyles: { fontSize: 10 },
    columnStyles: {
      0: { cellWidth: 80 },
      1: { halign: "right", cellWidth: 32 },
      2: { halign: "right", cellWidth: 38 },
      3: { halign: "right", cellWidth: 33 },
    },
    margin: { left: 14, right: 14 },
    showFoot: "lastPage",
  });

  // ── Pie de página ─────────────────────────────────────────────────────────
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(150);
    doc.text(`Página ${i} de ${pages}`, 197, 275, { align: "right" });
    doc.text("Servilla ERP", 14, 275);
    doc.setTextColor(0);
  }

  doc.save(`pegado_guias_${periodo.replace(/\s/g, "_")}.pdf`);
}
