import { useEffect, useState } from "react";
import api from "@/lib/api";

export const useFxQuote = (currency, date) => {
  const [state, setState] = useState({ quote: null, loading: true, error: "" });
  const [revision, setRevision] = useState(0);
  const key = `${currency}:${date}`;
  useEffect(() => {
    let current = true;
    setState({ key, quote: null, loading: true, error: "" });
    if (!currency || !date) { setState({ key, quote: null, loading: false, error: "Tarih ve pazar yeri seçin." }); return; }
    api.get("/fx/to-usd", { params: { currency, date } }).then(({ data }) => {
      if (current) setState({ key, quote: data, loading: false, error: "" });
    }).catch(err => {
      const detail = err.response?.data?.detail;
      if (current) setState({ key, quote: null, loading: false, error: typeof detail === "string" ? detail : "Kur alınamadı. Lütfen tekrar deneyin." });
    });
    return () => { current = false; };
  }, [currency, date, key, revision]);
  return { ...(state.key === key ? state : { quote: null, loading: true, error: "" }), retry: () => setRevision(v => v + 1) };
};