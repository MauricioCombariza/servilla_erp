# Búsqueda por código y "seleccionar todo" en /pagos-mensajeros

## Contexto

En `/pagos-mensajeros` (pestaña "Seleccionar", componente `SeleccionarTab` en
`frontend/src/pages/pagos/LiquidacionesPage.tsx:293-470`), el usuario elige una persona
en un `<select>` nativo que lista `Nombre (código) — tipo`, y luego marca uno por uno los
checkboxes de planillas pendientes y días de alistamiento pendientes que quiere incluir en
la liquidación.

Con muchas personas activas, buscar por nombre en el `<select>` es más lento que buscar por
código (que el usuario suele tener a mano). Y cuando se quiere liquidar todo lo pendiente de
una persona, marcar cada checkbox uno por uno es tedioso.

Este cambio es puramente de frontend — no toca endpoints ni schemas del backend. Las
fuentes de datos (`personalApi.list`, `liqApi.planillasPendientes`,
`laboresApi.resumenDiario`) ya traen todo lo necesario.

## Diseño

### 1. Combobox de búsqueda por nombre o código

Reemplaza el `<select>` nativo (líneas 349-357) por un nuevo subcomponente
`PersonaCombobox`, definido en el mismo archivo, con esta interfaz:

```ts
function PersonaCombobox({ personas, value, onChange }: {
  personas: Personal[]; value: number | ""; onChange: (id: number | "") => void;
}): JSX.Element
```

Comportamiento:

- Estado interno: `query` (texto escrito) y `open` (si la lista desplegable está visible).
- Mientras `value === ""` o `open === true`: se muestra un `<input type="text">` con la
  lista filtrada debajo (mismo contenedor `border border-gray-300 rounded-lg` que usa el
  resto del archivo para paneles). El filtro hace `includes()` case-insensitive contra
  `codigo` **y** `nombre_completo`, sin distinguir cuál matcheó — así "18" encuentra tanto
  código `0018` como un nombre que contenga "18".
- Al hacer click (con `onMouseDown`, no `onClick`, para que dispare antes que el `onBlur`
  del input) sobre una opción de la lista: llama `onChange(persona.id)`, limpia `query` y
  cierra la lista (`open = false`).
- Mientras hay una persona elegida (`value !== ""`) y `open === false`: el campo se ve como
  una "pill" de solo lectura con el texto `Nombre (código) — tipo` y un botón de texto
  "Cambiar" que pone `open = true` para volver a buscar.
- `onBlur` del input cierra la lista (con el `onMouseDown` de las opciones ya cubierto,
  no hace falta `setTimeout`).
- Sin dependencias nuevas — se implementa con `useState` puro, igual que el resto de
  `SeleccionarTab`.

El componente que lo usa (`SeleccionarTab`) sigue llamando `cambiarPersona(id)` en
`onChange`, que ya limpia `planillasSel`/`fechasSel` al cambiar de persona — ese
comportamiento no cambia.

### 2. Botón "Seleccionar todo" / "Deseleccionar todo"

Se agrega a la barra inferior existente (línea 436-448), junto al resumen
`"N planilla(s) · N día(s) · Total"` y antes del botón "Generar liquidación".

```ts
const totalItems = planillas.length + (soloSeriales ? 0 : dias.length);
const seleccionados = planillasSel.size + fechasSel.size;
const todoSeleccionado = totalItems > 0 && seleccionados === totalItems;

function toggleTodo() {
  if (todoSeleccionado) {
    setPlanillasSel(new Set());
    setFechasSel(new Set());
  } else {
    setPlanillasSel(new Set(planillas.map((p) => p.planilla)));
    setFechasSel(soloSeriales ? new Set() : new Set(dias.map((d) => d.fecha)));
  }
}
```

- Texto dinámico: `"Seleccionar todo"` / `"Deseleccionar todo"` según `todoSeleccionado`.
- `disabled` cuando `totalItems === 0` (no hay nada pendiente para esa persona).
- Estilo: botón secundario con borde, siguiendo el mismo patrón visual que "Aprobar todo"
  en `frontend/src/pages/labores/LaboresPage.tsx:198-208`
  (`border border-{color}-300 text-{color}-700 hover:bg-{color}-50`), usando un color
  neutro/azul (no verde, para no confundirlo con una acción de aprobación).

## Fuera de alcance

- No cambia el endpoint de generación (`liqApi.generar`) ni el modal de confirmación
  (`ConfirmarLiquidacionModal`).
- No agrega selección múltiple de personas (se sigue liquidando de a una persona por vez).
- No toca el resto de pestañas de `LiquidacionesPage.tsx` ("Pendientes de liquidar",
  "Liquidaciones generadas") ni el flujo legado usado por `NominaPage`/`LaboresPage`.

## Verificación

1. `npx tsc -b --noEmit` sin errores.
2. Manual en navegador (`/pagos-mensajeros` → pestaña "Seleccionar"):
   - Escribir un código (ej. `0018`) en el combobox y confirmar que filtra a esa persona.
   - Escribir parte de un nombre y confirmar que también filtra.
   - Elegir una persona, click "Cambiar", confirmar que reabre la búsqueda sin perder la
     lista de personas.
   - Con planillas y días pendientes visibles, click "Seleccionar todo": todos los
     checkboxes quedan marcados y el botón pasa a "Deseleccionar todo".
   - Click de nuevo: todos los checkboxes se desmarcan.
   - Generar una liquidación de prueba con selección hecha vía "Seleccionar todo" y
     confirmar que el monto coincide con la suma mostrada.
