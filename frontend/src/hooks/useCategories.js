import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";

/**
 * Loads store-scoped transaction categories (default + user-defined).
 * Returns helpers for filtering by section/type and a refresh callback.
 */
export const useCategories = (storeId) => {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!storeId) {
      setCategories([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/categories", { params: { store_id: storeId } });
      setCategories(data);
    } catch (err) {
      setError(err?.response?.data?.detail || "Kategoriler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { refresh(); }, [refresh]);

  const bySection = (section) => categories.filter((c) => c.section === section && !c.archived);
  const byType = (type, section) => categories.filter((c) => c.type === type && (!section || c.section === section) && !c.archived);

  return { categories, loading, error, refresh, bySection, byType };
};
