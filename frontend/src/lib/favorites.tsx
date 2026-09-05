import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { storage } from "@/src/utils/storage";

const KEY = "food_favorites";

type FavCtx = { favorites: string[]; toggle: (id: string) => void; isFav: (id: string) => boolean };
const Ctx = createContext<FavCtx>({ favorites: [], toggle: () => {}, isFav: () => false });

export function FavoritesProvider({ children }: { children: React.ReactNode }) {
  const [favorites, setFavorites] = useState<string[]>([]);

  useEffect(() => {
    (async () => {
      const saved = await storage.getItem<string[]>(KEY, []);
      setFavorites(saved ?? []);
    })();
  }, []);

  const toggle = useCallback((id: string) => {
    setFavorites((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      storage.setItem(KEY, next);
      return next;
    });
  }, []);

  const isFav = useCallback((id: string) => favorites.includes(id), [favorites]);

  return <Ctx.Provider value={{ favorites, toggle, isFav }}>{children}</Ctx.Provider>;
}

export const useFavorites = () => useContext(Ctx);
