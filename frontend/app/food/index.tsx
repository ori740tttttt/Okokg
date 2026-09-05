import React, { useMemo, useState } from "react";
import { View, Text, Pressable, FlatList } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { router } from "expo-router";
import Animated, { FadeInDown } from "react-native-reanimated";

import { Header } from "@/src/components/Header";
import { ChipRow, EmptyState } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { culinaryData } from "@/src/lib/culinary";
import { useDishes, foodCategories, MergedDish } from "@/src/lib/dishes";
import { useFavorites } from "@/src/lib/favorites";

export default function FoodList() {
  const s = useStyles();
  const { colors } = useTheme();
  const { favorites, toggle, isFav } = useFavorites();
  const dishes = useDishes();
  const [cat, setCat] = useState("All");
  const [favOnly, setFavOnly] = useState(false);

  const chips = foodCategories.map((c) => ({ key: c, label: c === "All" ? "Tutte" : c }));

  const filtered = useMemo(() => {
    let list = dishes.data ?? [];
    if (favOnly) list = list.filter((d) => favorites.includes(d.id));
    if (cat !== "All") list = list.filter((d) => d.category === cat);
    return list;
  }, [cat, favOnly, favorites, dishes.data]);

  const renderItem = ({ item, index }: { item: MergedDish; index: number }) => {
    const fav = isFav(item.id);
    return (
      <Animated.View entering={FadeInDown.delay((index % 8) * 40)} style={s.cell}>
        <Pressable
          testID={`dish-${item.id}`}
          style={s.card}
          onPress={() => router.push({ pathname: "/food/[id]", params: { id: item.id } })}
        >
          <View style={s.glyphWrap}>
            {item.image ? (
              <>
                <Image source={{ uri: item.image }} style={s.thumbImg} contentFit="cover" transition={200} />
                <LinearGradient colors={["transparent", "rgba(44,42,40,0.35)"]} style={s.thumbShade} />
                <Text style={s.glyphBadge}>{item.icon}</Text>
              </>
            ) : (
              <Text style={s.glyph}>{item.icon}</Text>
            )}
            <Pressable
              testID={`fav-${item.id}`}
              onPress={() => toggle(item.id)}
              hitSlop={10}
              style={[s.heart, fav && { backgroundColor: colors.error + "22" }]}
            >
              <Icon name={fav ? "heart" : "heart-outline"} size={16} color={fav ? colors.error : colors.muted} />
            </Pressable>
          </View>
          <Text style={s.name} numberOfLines={2}>
            {item.name}
          </Text>
          <View style={s.regionRow}>
            <Icon name="map-marker" size={12} color={colors.olive} />
            <Text style={s.region} numberOfLines={1}>
              {item.region}
            </Text>
          </View>
        </Pressable>
      </Animated.View>
    );
  };

  return (
    <View style={s.screen}>
      <Header
        title="Cucina Siciliana"
        kicker="Palermo & Trapani"
        showBack
        right={
          <Pressable
            testID="fav-filter"
            onPress={() => setFavOnly((v) => !v)}
            style={[s.favFilter, favOnly && { backgroundColor: colors.error + "22", borderColor: colors.error }]}
            hitSlop={6}
          >
            <Icon name={favOnly ? "heart" : "heart-outline"} size={18} color={favOnly ? colors.error : colors.onSurfaceTertiary} />
          </Pressable>
        }
      />
      <FlatList
        testID="food-list"
        data={filtered}
        keyExtractor={(d) => d.id}
        renderItem={renderItem}
        numColumns={2}
        columnWrapperStyle={{ gap: spacing.sm, paddingHorizontal: spacing.md }}
        contentContainerStyle={{ paddingBottom: spacing.xxl, gap: spacing.sm }}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={
          <View>
            <View style={s.cover}>
              <LinearGradient colors={[colors.brandPrimary, colors.olive]} style={s.coverBg} />
              <View style={s.coverContent}>
                <Icon name="silverware-fork-knife" size={28} color="#fff" />
                <Text style={s.coverTitle}>Guida ai sapori del territorio</Text>
                <Text style={s.coverSub}>
                  {culinaryData.length} specialità tradizionali, dai mercati di Palermo alle coste di Trapani, Erice e Pantelleria.
                </Text>
              </View>
            </View>
            <ChipRow items={chips} selected={cat} onSelect={setCat} />
          </View>
        }
        ListEmptyComponent={
          <EmptyState icon="heart-off-outline" title="Nessun piatto" subtitle={favOnly ? "Aggiungi i tuoi preferiti col cuore" : "Nessun risultato"} />
        }
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  favFilter: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: c.border },
  cover: { margin: spacing.md, borderRadius: radius.lg, overflow: "hidden", minHeight: 130 },
  coverBg: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  coverContent: { padding: spacing.lg, gap: 6 },
  coverTitle: { color: "#fff", fontSize: 22, fontFamily: fonts.heading, marginTop: 4 },
  coverSub: { color: "rgba(255,255,255,0.9)", fontSize: 13, lineHeight: 19, fontFamily: fonts.body },
  cell: { flex: 1 },
  card: { flex: 1, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: c.border, gap: 6 },
  glyphWrap: { height: 110, backgroundColor: c.surfaceTertiary, borderRadius: radius.md, overflow: "hidden", alignItems: "center", justifyContent: "center" },
  glyph: { fontSize: 44 },
  thumbImg: { ...({ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 } as const) },
  thumbShade: { position: "absolute", left: 0, right: 0, bottom: 0, height: 50 },
  glyphBadge: { position: "absolute", left: 6, bottom: 6, fontSize: 22 },
  heart: { position: "absolute", top: 6, right: 6, width: 30, height: 30, borderRadius: radius.pill, backgroundColor: c.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  name: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading, lineHeight: 18, marginTop: 2 },
  regionRow: { flexDirection: "row", alignItems: "center", gap: 3 },
  region: { color: c.muted, fontSize: 11, fontFamily: fonts.body, flexShrink: 1 },
}));
