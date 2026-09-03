export function CurrencyCell({
  value,
  negativeRed = false,
}: {
  value: number | null | undefined;
  negativeRed?: boolean;
}) {
  if (value == null) return <span className="text-gray-400">—</span>;
  return (
    <span className={negativeRed && value < 0 ? "text-red-600" : undefined}>
      ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(value)}
    </span>
  );
}
