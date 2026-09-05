import React from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { Icon } from "./Icon";
import type { Poi } from "@/src/lib/queries";

// Web fallback: react-native-maps does not run on web. Show a tappable pin grid
// so the itinerary builder still works fully in the browser preview.
export function PoiMap({
  pois,
  selectedIds,
  onPressPoi,
  tintFor,
}: {
  pois: Poi[];
  selectedIds: string[];
  onPressPoi: (p: Poi) => void;
  tintFor: (cat: string) => string;
}) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View style={s.wrap}>
      <View style={s.banner}>
        <Icon name="map-outline" size={16} color={colors.muted} />
        <Text style={s.bannerTxt}>Mappa nativa nell{"'"}app · tocca un punto per i dettagli</Text>
      </View>
      <ScrollView contentContainerStyle={s.grid} showsVerticalScrollIndicator={false}>
        {pois.map((p) => {
          const active = selectedIds.includes(p.id);
          return (
            <Pressable
              key={p.id}
              testID={`marker-${p.id}`}
              style={[s.pin, { borderColor: active ? colors.brandPrimary : colors.border, backgroundColor: active ? colors.brandPrimary + "18" : colors.surfaceSecondary }]}
              onPress={() => onPressPoi(p)}
            >
              <Icon name="map-marker" size={18} color={active ? colors.brandPrimary : tintFor(p.category)} />
              <Text style={s.pinTxt} numberOfLines={1}>{p.name}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: { flex: 1, backgroundColor: c.surfaceTertiary },
  banner: { flexDirection: "row", alignItems: "center", gap: 6, padding: spacing.sm, backgroundColor: c.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: c.divider },
  bannerTxt: { color: c.muted, fontSize: 11, fontFamily: fonts.body, flexShrink: 1 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 6, padding: spacing.sm },
  pin: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: radius.pill, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 6, maxWidth: "48%" },
  pinTxt: { color: c.onSurface, fontSize: 12, fontFamily: fonts.body, flexShrink: 1 },
}));
