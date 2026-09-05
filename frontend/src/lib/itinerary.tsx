import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { storage } from "@/src/utils/storage";

const KEY = "my_itinerary";

type ItinCtx = {
  ids: string[];
  toggle: (id: string) => void;
  remove: (id: string) => void;
  clear: () => void;
  has: (id: string) => boolean;
};
const Ctx = createContext<ItinCtx>({ ids: [], toggle: () => {}, remove: () => {}, clear: () => {}, has: () => false });

export function ItineraryProvider({ children }: { children: React.ReactNode }) {
  const [ids, setIds] = useState<string[]>([]);

  useEffect(() => {
    (async () => {
      const saved = await storage.getItem<string[]>(KEY, []);
      setIds(saved ?? []);
    })();
  }, []);

  const persist = (next: string[]) => {
    storage.setItem(KEY, next);
    return next;
  };

  const toggle = useCallback((id: string) => {
    setIds((prev) => persist(prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, []);

  const remove = useCallback((id: string) => {
    setIds((prev) => persist(prev.filter((x) => x !== id)));
  }, []);

  const clear = useCallback(() => setIds(() => persist([])), []);

  const has = useCallback((id: string) => ids.includes(id), [ids]);

  return <Ctx.Provider value={{ ids, toggle, remove, clear, has }}>{children}</Ctx.Provider>;
}

export const useItinerary = () => useContext(Ctx);
