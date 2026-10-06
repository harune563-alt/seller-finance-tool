import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { apiError } from "@/components/company/Fields";

export const useCompanyResource = path => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(v => v + 1), []);
  useEffect(() => {
    let current = true; setData(null); setError(""); setLoading(!!path);
    if (!path) return;
    api.get(path).then(r => { if (current) setData(r.data); }).catch(e => { if (current) setError(apiError(e)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [path, revision]);
  return { data, loading, error, refresh };
};