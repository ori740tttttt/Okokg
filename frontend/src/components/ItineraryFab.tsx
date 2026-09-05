import React from "react";
import { Pressable, Text, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { Icon } from "./Icon";
import { useItinerary } from "@/src/lib/itinerary";

// Floating "Il mio itinerario" pill shown over guest screens. Opens the map tab.
export function ItineraryFab() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { ids } = useItinerary();

  if (ids.length === 0) return null;

  return (
    <Pressable
      testID="itinerary-fab"
      style={[s.fab, { bottom: Math.max(insets.bottom, 12) + 12 }]}
      onPress={() => router.push("/(guest)/map")}
    >
      <Icon name="playlist-edit" size={20} color={colors.onBrandPrimary} />
      <Text style={s.txt}>Il mio itinerario</Text>
      <View style={s.badge}>
        <Text style={s.badgeTxt}>{ids.length}</Text>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((c) => ({
  fab: {
    position: "absolute",
    right: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: c.brandPrimary,
    borderRadius: radius.pill,
    paddingLeft: spacing.md,
    paddingRight: 6,
    paddingVertical: 10,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 6,
  },
  txt: { color: c.onBrandPrimary, fontSize: 14, fontFamily: fonts.heading },
  badge: { minWidth: 24, height: 24, borderRadius: 12, backgroundColor: "rgba(255,255,255,0.25)", alignItems: "center", justifyContent: "center", paddingHorizontal: 6 },
  badgeTxt: { color: c.onBrandPrimary, fontSize: 13, fontFamily: fonts.heading },
}));
