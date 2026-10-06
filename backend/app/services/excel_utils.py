from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# (nombre_hoja, titulo, columnas, filas, widths)
Hoja = tuple[str, str, list[str], list[dict], list[int]]


def construir_excel(titulo: str, columnas: list[str], filas: list[dict], widths: list[int]) -> bytes:
    return construir_excel_multi([("Datos", titulo, columnas, filas, widths)])


def construir_excel_multi(hojas: list[Hoja], formatos: dict[str, str] | None = None) -> bytes:
    """Un libro con una hoja por elemento de `hojas`.

    `formatos` mapea nombre de columna → number_format de openpyxl (p.ej. "#,##0")
    y aplica a cualquier hoja que tenga esa columna.
    """
    formatos = formatos or {}
    wb = Workbook()
    wb.remove(wb.active)

    for nombre_hoja, titulo, columnas, filas, widths in hojas:
        ws = wb.create_sheet(nombre_hoja)

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columnas))
        ws.cell(row=1, column=1, value=titulo).font = Font(bold=True, size=13)

        header_row = 3
        for col, nombre_col in enumerate(columnas, start=1):
            c = ws.cell(row=header_row, column=col, value=nombre_col)
            c.font = Font(bold=True)
            c.alignment = Alignment(horizontal="center")

        row_idx = header_row + 1
        for fila in filas:
            for col, key in enumerate(columnas, start=1):
                c = ws.cell(row=row_idx, column=col, value=fila.get(key))
                if key in formatos:
                    c.number_format = formatos[key]
            row_idx += 1

        for col, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = w

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
