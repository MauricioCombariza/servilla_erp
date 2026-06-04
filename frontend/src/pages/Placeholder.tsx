import { useLocation } from "react-router-dom";

export function Placeholder() {
  const { pathname } = useLocation();
  return (
    <div className="flex flex-col items-center justify-center py-24 text-gray-400">
      <p className="text-lg font-medium">En construcción</p>
      <p className="text-sm mt-1">{pathname}</p>
    </div>
  );
}
