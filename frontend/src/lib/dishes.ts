import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { culinaryData, Dish, foodCategories } from "./culinary";

export type MergedDish = Dish & { image?: string; hidden?: boolean; custom?: boolean };
export type DishOverride = Partial<MergedDish> & { id: string };

async function fetchOverrides(): Promise<DishOverride[]> {
  try {
    const res = await api.get<DishOverride[]>("/dishes/overrides");
    return res.data ?? [];
  } catch {
    return [];
  }
}

export function mergeDishes(overrides: DishOverride[]): MergedDish[] {
  const byId = new Map<string, MergedDish>();
  for (const d of culinaryData) byId.set(d.id, { ...d });
  for (const o of overrides) {
    const base = byId.get(o.id);
    if (base) byId.set(o.id, { ...base, ...clean(o) });
    else byId.set(o.id, { ...emptyDish(o.id), ...clean(o), custom: true });
  }
  return Array.from(byId.values()).filter((d) => !d.hidden);
}

function clean(o: DishOverride): Partial<MergedDish> {
  const out: any = {};
  for (const [k, v] of Object.entries(o)) if (v !== null && v !== undefined) out[k] = v;
  return out;
}

function emptyDish(id: string): MergedDish {
  return { id, category: "Palermo", name: "", region: "", description: "", ingredients: [], funFact: "", icon: "🍽️" };
}

export function useDishes() {
  return useQuery({
    queryKey: ["dishes"],
    queryFn: fetchOverrides,
    select: (overrides) => mergeDishes(overrides),
  });
}

export { foodCategories, culinaryData };
export type { Dish };
