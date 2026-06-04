interface BadgeProps {
  active: boolean;
  activeLabel?: string;
  inactiveLabel?: string;
}

export function Badge({ active, activeLabel = "Activo", inactiveLabel = "Inactivo" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        active ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
      }`}
    >
      {active ? activeLabel : inactiveLabel}
    </span>
  );
}
