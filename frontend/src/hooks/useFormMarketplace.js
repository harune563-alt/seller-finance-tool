import { useState } from "react";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE } from "@/constants/marketplaces";

export const useFormMarketplace = () => {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const options = activeStore?.marketplaces || [];
  const scope = `${activeStoreId}:${activeMarketplace}:${options.join(",")}`;
  const [choice, setChoice] = useState(null);
  const preferred = options.includes(activeMarketplace) ? activeMarketplace : options[0] || "";
  const marketplace = choice?.scope === scope && options.includes(choice.value) ? choice.value : preferred;
  const selectMarketplace = value => {
    // Radix's hidden native select can emit an empty change during a form/options reset.
    if (options.includes(value)) setChoice({ scope, value });
  };
  return { marketplace, currency: MP_BY_CODE[marketplace]?.currency || "", selectMarketplace };
};