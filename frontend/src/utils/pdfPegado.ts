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

  // ── Agrupar: fecha → persona → {cantidad, tarifa, total} ─────────────────
  const porFecha = new Map<string, Map<string, { cantidad: number; tarifa: number; total: number }>>();
  for (const f of filas) {
    if (!porFecha.has(f.fecha)) porFecha.set(f.fecha, new Map());
    const porPersona = porFecha.get(f.fecha)!;
    const prev = porPersona.get(f.personal_nombre);
    if (prev) {
      prev.cantidad += f.cantidad;
      prev.total    += f.total;
    } else {
      porPersona.set(f.personal_nombre, { cantidad: f.cantidad, tarifa: f.tarifa_unitaria, total: f.total });
    }
  }

  const fechasOrdenadas = [...porFecha.keys()].sort();
  let totalGenGuias = 0;
  let totalGenValor = 0;
  let y = 38;

  for (const fecha of fechasOrdenadas) {
    const porPersona = porFecha.get(fecha)!;
    const rows = [...porPersona.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const totalGuiasDia = rows.reduce((s, [, v]) => s + v.cantidad, 0);
    const totalValorDia = rows.reduce((s, [, v]) => s + v.total, 0);
    totalGenGuias += totalGuiasDia;
    totalGenValor += totalValorDia;

    // Encabezado de fecha
    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.setFillColor(230, 230, 250);
    doc.rect(14, y, 183, 7, "F");
    doc.setTextColor(40, 40, 120);
    doc.text(
      `${fecha}   ·   ${fmtNum(totalGuiasDia)} guías   ·   ${fmtCop(totalValorDia)}`,
      16, y + 5
    );
    doc.setTextColor(0);
    y += 9;

    autoTable(doc, {
      startY: y,
      head: [["Personal", "Guías pegadas", "Tarifa / guía", "Total"]],
      body: rows.map(([nombre, v]) => [
        nombre,
        fmtNum(v.cantidad),
        fmtCop(v.tarifa),
        fmtCop(v.total),
      ]),
      foot: [[
        { content: "Subtotal día", styles: { fontStyle: "bold" } },
        { content: fmtNum(totalGuiasDia), styles: { fontStyle: "bold" } },
        "",
        { content: fmtCop(totalValorDia), styles: { fontStyle: "bold" } },
      ]],
      theme: "striped",
      headStyles: { fillColor: [63, 81, 181], fontSize: 9, fontStyle: "bold" },
      footStyles: { fillColor: [220, 220, 235], textColor: [30, 30, 30], fontSize: 9 },
      bodyStyles: { fontSize: 9 },
      columnStyles: {
        0: { cellWidth: 80 },
        1: { halign: "right", cellWidth: 32 },
        2: { halign: "right", cellWidth: 38 },
        3: { halign: "right", cellWidth: 33 },
      },
      margin: { left: 14, right: 14 },
      showFoot: "lastPage",
    });

    y = (doc as jsPDF & { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;

    if (y > 240 && fechasOrdenadas.indexOf(fecha) < fechasOrdenadas.length - 1) {
      doc.addPage();
      y = 18;
    }
  }

  // ── Total general del mes ─────────────────────────────────────────────────
  if (y > 250) { doc.addPage(); y = 18; }

  doc.setFontSize(10);
  doc.setFont("helvetica", "bold");
  doc.setFillColor(63, 81, 181);
  doc.setTextColor(255, 255, 255);
  doc.rect(14, y, 183, 9, "F");
  doc.text("TOTAL MES", 16, y + 6);
  doc.text(fmtNum(totalGenGuias) + " guías", 110, y + 6, { align: "right" });
  doc.text(fmtCop(totalGenValor), 197, y + 6, { align: "right" });
  doc.setTextColor(0);

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
