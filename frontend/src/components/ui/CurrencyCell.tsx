export function CurrencyCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-gray-400">—</span>;
  return (
    <span>
      ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(value)}
    </span>
  );
}
