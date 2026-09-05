import React, { useMemo, useState } from "react";
import { View, Text, Pressable, FlatList, Linking } from "react-native";
import { Image } from "expo-image";
import { useTranslation } from "react-i18next";
import { router } from "expo-router";

import { Header } from "@/src/components/Header";
import { ChipRow, EmptyState, Loading, Field } from "@/src/components/ui";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { usePois, Poi } from "@/src/lib/queries";
import { useItinerary } from "@/src/lib/itinerary";
import { ItineraryFab } from "@/src/components/ItineraryFab";

const CATEGORY_META: Record<string, { icon: IconName; color: (c: any) => string }> = {
  art: { icon: "bank", color: (c) => c.brandPrimary },
  beach: { icon: "beach", color: (c) => c.info },
  nature: { icon: "pine-tree", color: (c) => c.olive },
};

export default function PlacesScreen() {
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const pois = usePois();
  const { has, toggle } = useItinerary();
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");

  const chips = [
    { key: "all", label: t("map_page.title"), icon: "map-marker-multiple" as IconName },
    { key: "art", label: t("map_page.categories.art"), icon: "bank" as IconName },
    { key: "beach", label: t("map_page.categories.beach"), icon: "beach" as IconName },
    { key: "nature", label: t("map_page.categories.nature"), icon: "pine-tree" as IconName },
  ];

  const filtered = useMemo(() => {
    let list = pois.data ?? [];
    if (cat !== "all") list = list.filter((p) => p.category === cat);
    if (q.trim()) {
      const needle = q.toLowerCase();
      list = list.filter(
        (p) => p.name.toLowerCase().includes(needle) || (p.town ?? "").toLowerCase().includes(needle),
      );
    }
    return list;
  }, [pois.data, cat, q]);

  const openDirections = (p: Poi) => {
    const url = p.maps_url || `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}`;
    Linking.openURL(url).catch(() => {});
  };

  const renderItem = ({ item }: { item: Poi }) => {
    const meta = CATEGORY_META[item.category] ?? CATEGORY_META.art;
    return (
      <Pressable
        testID={`poi-${item.id}`}
        style={s.card}
        onPress={() => router.push({ pathname: "/place/[id]", params: { id: item.id } })}
      >
        <View style={[s.thumb, { backgroundColor: colors.surfaceTertiary }]}>
          {item.image_url ? (
            <Image source={{ uri: item.image_url }} style={s.thumbImg} contentFit="cover" />
          ) : (
            <Icon name={meta.icon} size={26} color={meta.color(colors)} />
          )}
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.cardTitle} numberOfLines={1}>
            {item.name}
          </Text>
          <View style={s.metaRow}>
            <Icon name="map-marker" size={13} color={colors.muted} />
            <Text style={s.metaTxt} numberOfLines={1}>
              {item.town ?? item.province ?? "Sicilia"}
            </Text>
          </View>
          {item.description ? (
            <Text style={s.cardDesc} numberOfLines={2}>
              {item.description}
            </Text>
          ) : null}
        </View>
        <Pressable testID={`poi-add-${item.id}`} onPress={() => toggle(item.id)} style={[s.dirBtn, has(item.id) && { backgroundColor: colors.brandPrimary }]} hitSlop={8}>
          <Icon name={has(item.id) ? "playlist-remove" : "playlist-plus"} size={20} color={has(item.id) ? colors.onBrandPrimary : colors.brandPrimary} />
        </Pressable>
        <Pressable testID={`poi-dir-${item.id}`} onPress={() => openDirections(item)} style={s.dirBtn} hitSlop={8}>
          <Icon name="directions" size={20} color={colors.olive} />
        </Pressable>
      </Pressable>
    );
  };

  return (
    <View style={s.screen}>
      <Header title={t("map_page.title")} kicker={t("map_page.kicker")} />
      <View style={s.searchWrap}>
        <Field value={q} onChangeText={setQ} placeholder={t("map_page.search_placeholder")} icon="magnify" testID="poi-search" />
      </View>
      <ChipRow items={chips} selected={cat} onSelect={setCat} />
      {pois.isLoading ? (
        <Loading />
      ) : (
        <FlatList
          testID="poi-list"
          data={filtered}
          keyExtractor={(p) => p.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl, gap: spacing.sm }}
          ListHeaderComponent={<Text style={s.count}>{filtered.length} {t("map_page.itinerary_count")}</Text>}
          ListEmptyComponent={<EmptyState icon="map-search-outline" title={t("map_page.no_results")} />}
          showsVerticalScrollIndicator={false}
        />
      )}
      <ItineraryFab />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  searchWrap: { paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  count: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginBottom: spacing.sm, textTransform: "uppercase", letterSpacing: 1 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: c.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: c.border,
  },
  thumb: { width: 64, height: 64, borderRadius: radius.md, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  thumbImg: { width: "100%", height: "100%" },
  cardTitle: { color: c.onSurface, fontSize: 16, fontFamily: fonts.heading },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  metaTxt: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  cardDesc: { color: c.onSurfaceSecondary, fontSize: 13, marginTop: 4, fontFamily: fonts.body, lineHeight: 18 },
  dirBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
}));
