import { useEffect, useState } from "react";
import { laboresApi } from "@/api/labores";

export function usePersonalLookup() {
  const [codigo, setCodigo] = useState("");
  const [info, setInfo] = useState<{ id: number; nombre_completo: string } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (codigo.length !== 4) {
      setInfo(null);
      setError(false);
      return;
    }
    let cancelled = false;
    laboresApi
      .lookupPersonalCodigo(codigo)
      .then((r) => {
        if (!cancelled) {
          setInfo(r.data);
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setInfo(null);
          setError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [codigo]);

  return {
    codigo,
    setCodigo,
    info,
    error,
    reset: () => {
      setCodigo("");
      setInfo(null);
      setError(false);
    },
  };
}
