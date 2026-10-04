import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const StoreContext = createContext(null);

export const StoreProvider = ({ children }) => {
  const { user } = useAuth();
  const [stores, setStores] = useState([]);
  const [activeStoreId, setActiveStoreId] = useState(() => localStorage.getItem("amz_store") || "");
  const [activeMarketplace, setActiveMarketplace] = useState(() => localStorage.getItem("amz_mp") || "ALL");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user || user === false) return;
    try {
      const { data } = await api.get("/stores");
      setStores(data);
      if (data.length && !data.find((s) => s.id === activeStoreId)) {
        setActiveStoreId(data[0].id);
      }
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [user, activeStoreId]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (activeStoreId) localStorage.setItem("amz_store", activeStoreId);
  }, [activeStoreId]);
  useEffect(() => {
    localStorage.setItem("amz_mp", activeMarketplace);
  }, [activeMarketplace]);

  const activeStore = stores.find((s) => s.id === activeStoreId) || null;

  return (
    <StoreContext.Provider value={{
      stores, activeStore, activeStoreId, setActiveStoreId,
      activeMarketplace, setActiveMarketplace, loading, refresh,
    }}>
      {children}
    </StoreContext.Provider>
  );
};

export const useStore = () => useContext(StoreContext);
