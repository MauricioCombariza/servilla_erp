from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.devoluciones import DevolucionDocumentoItem
from app.services.devoluciones_docx import FOOTER_GRAPHIC, HEADER_LOGO, _fecha_es

PDF_MEDIA_TYPE = "application/pdf"

_PAGE_WIDTH, _PAGE_HEIGHT = letter
_HEADER_ASPECT = 338 / 1426  # alto/ancho real de header_logo.png
_FOOTER_ASPECT = 590 / 340  # alto/ancho real de footer_graphic.png


def _dibujar_footer(canvas, _doc) -> None:
    if not FOOTER_GRAPHIC.exists():
        return
    ancho = 0.9 * inch
    alto = ancho * _FOOTER_ASPECT
    canvas.saveState()
    canvas.drawImage(
        str(FOOTER_GRAPHIC),
        (_PAGE_WIDTH - ancho) / 2,
        0.25 * inch,
        width=ancho,
        height=alto,
        mask="auto",
        preserveAspectRatio=True,
    )
    canvas.restoreState()


def construir_pdf_devolucion(items: list[DevolucionDocumentoItem], fecha: date) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=1.1 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
    )

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "TituloActa", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=16, spaceAfter=4,
    )
    sub_style = ParagraphStyle("SubActa", parent=styles["Normal"], alignment=TA_CENTER)

    contenido_ancho = _PAGE_WIDTH - 1.4 * inch

    elementos = []
    if HEADER_LOGO.exists():
        ancho_header = min(5.5 * inch, contenido_ancho)
        elementos.append(
            Image(str(HEADER_LOGO), width=ancho_header, height=ancho_header * _HEADER_ASPECT, hAlign="CENTER")
        )
        elementos.append(Spacer(1, 14))

    elementos.append(Paragraph("ACTA DE DEVOLUCIÓN", titulo_style))
    elementos.append(Paragraph(f"Fecha: {_fecha_es(fecha)}", sub_style))
    elementos.append(Spacer(1, 18))

    data = [["Serial", "Nombre", "Dirección", "Localidad"]]
    for item in items:
        data.append([item.serial, item.nombre or "", item.direccion or "", item.localidad or ""])

    tabla = Table(
        data,
        colWidths=[1.4 * inch, 1.7 * inch, 2.4 * inch, 1.4 * inch],
        repeatRows=1,
    )
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d550e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 40))

    firma_style = ParagraphStyle("Firma", parent=styles["Normal"], alignment=TA_CENTER)
    elementos.append(Paragraph("_" * 40, firma_style))

    doc.build(elementos, onFirstPage=_dibujar_footer, onLaterPages=_dibujar_footer)
    return buffer.getvalue()
