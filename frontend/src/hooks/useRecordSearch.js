import { useEffect, useState } from "react";
import api from "@/lib/api";

const defaults = () => ({ search: "", start_date: "", end_date: "", category: "" });
export const useRecordSearch = ({ storeId, marketplace, currency, view, revision, outcome = "all" }) => {
  const [filters, setFilters] = useState(defaults);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState({ items: [], total: 0, total_pages: 1, loading: false, error: "" });
  useEffect(() => { const timer = setTimeout(() => setDebouncedSearch(filters.search.trim()), 300); return () => clearTimeout(timer); }, [filters.search]);
  useEffect(() => { setFilters(defaults()); setDebouncedSearch(""); setPage(1); }, [storeId, marketplace, currency]);
  useEffect(() => { setPage(1); }, [outcome]);
  const invalidDate = filters.start_date && filters.end_date && filters.start_date > filters.end_date;
  const key = JSON.stringify([storeId, marketplace, currency, view, filters.start_date, filters.end_date, filters.category, debouncedSearch, outcome, page, revision, retry]);
  useEffect(() => {
    let current = true;
    setState({ key, items: [], total: 0, total_pages: 1, loading: !!storeId, error: "" });
    if (!storeId || invalidDate) { setState({ key, items: [], total: 0, total_pages: 1, loading: false, error: invalidDate ? "Başlangıç tarihi bitiş tarihinden sonra olamaz." : "" }); return; }
    const params = { store_id: storeId, marketplace, currency: currency || "ALL", view, search: debouncedSearch, outcome, page, page_size: 20 };
    if (filters.start_date) params.start_date = filters.start_date;
    if (filters.end_date) params.end_date = filters.end_date;
    if (filters.category) params.category = filters.category;
    api.get("/transactions/search", { params }).then(({ data }) => {
      if (current) { setState({ ...data, key, loading: false, error: "" }); if (data.page !== page) setPage(data.page); }
    }).catch(err => {
      const detail = err.response?.data?.detail;
      if (current) setState({ key, items: [], total: 0, total_pages: 1, loading: false, error: typeof detail === "string" ? detail : "İşlem listesi yüklenemedi. Tekrar deneyin." });
    });
    return () => { current = false; };
  }, [key, storeId, marketplace, currency, view, filters.start_date, filters.end_date, filters.category, debouncedSearch, outcome, page, invalidDate]);
  const pending = state.key !== key || filters.search.trim() !== debouncedSearch;
  return {
    ...state, items: pending ? [] : state.items, total: pending ? 0 : state.total, loading: pending || state.loading,
    filters, page, setPage, invalidDate,
    change: (field, value) => { setFilters(f => ({ ...f, [field]: value })); setPage(1); },
    clear: () => { setFilters(defaults()); setDebouncedSearch(""); setPage(1); },
    retry: () => setRetry(v => v + 1),
  };
};