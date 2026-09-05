import React from "react";
import { ScrollView, View, Text, Pressable } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams } from "expo-router";

import { Header } from "@/src/components/Header";
import { Card, EmptyState } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { culinaryData } from "@/src/lib/culinary";
import { useDishes } from "@/src/lib/dishes";
import { useFavorites } from "@/src/lib/favorites";

export default function FoodDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStyles();
  const { colors } = useTheme();
  const { isFav, toggle } = useFavorites();
  const dishes = useDishes();
  const dish = (dishes.data ?? culinaryData).find((d) => d.id === id);

  if (!dish) {
    return (
      <View style={s.screen}>
        <Header title="—" showBack showLang={false} />
        <EmptyState icon="silverware-variant" title="Piatto non trovato" />
      </View>
    );
  }

  const fav = isFav(dish.id);

  return (
    <View style={s.screen}>
      <Header
        title={dish.name}
        showBack
        showLang={false}
        right={
          <Pressable
            testID="dish-fav"
            onPress={() => toggle(dish.id)}
            style={[s.heart, fav && { backgroundColor: colors.error + "22", borderColor: colors.error }]}
            hitSlop={6}
          >
            <Icon name={fav ? "heart" : "heart-outline"} size={20} color={fav ? colors.error : colors.onSurfaceTertiary} />
          </Pressable>
        }
      />
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxl }} showsVerticalScrollIndicator={false}>
        <View style={s.hero}>
          {dish.image ? (
            <>
              <Image source={{ uri: dish.image }} style={s.heroBg} contentFit="cover" transition={250} />
              <LinearGradient colors={["rgba(44,42,40,0.15)", "rgba(44,42,40,0.55)"]} style={s.heroBg} />
            </>
          ) : (
            <LinearGradient colors={[colors.brandPrimary, colors.olive]} style={s.heroBg} />
          )}
          <Text style={s.glyph}>{dish.icon}</Text>
        </View>

        <View style={s.body}>
          <View style={s.regionBadge}>
            <Icon name="map-marker" size={14} color={colors.onBrandPrimary} />
            <Text style={s.regionTxt}>{dish.region}</Text>
          </View>
          <Text style={s.title}>{dish.name}</Text>

          <Card style={{ marginTop: spacing.md }}>
            <View style={s.sectionHead}>
              <Icon name="silverware-fork-knife" size={20} color={colors.brand} />
              <Text style={s.sectionTitle}>Il piatto tradizionale</Text>
            </View>
            <Text style={s.desc}>{dish.description}</Text>
          </Card>

          <Card style={{ marginTop: spacing.md }}>
            <View style={s.sectionHead}>
              <Icon name="basket-outline" size={20} color={colors.olive} />
              <Text style={s.sectionTitle}>Ingredienti chiave</Text>
            </View>
            <View style={{ gap: spacing.sm, marginTop: spacing.sm }}>
              {dish.ingredients.map((ing) => (
                <View key={ing} style={s.ingRow}>
                  <View style={s.dot} />
                  <Text style={s.ingTxt}>{ing}</Text>
                </View>
              ))}
            </View>
          </Card>

          <View style={s.funCard}>
            <Icon name="information-outline" size={20} color={colors.brand} />
            <Text style={s.funLabel}>Curiosità per il turista</Text>
            <Text style={s.funTxt}>“{dish.funFact}”</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  heart: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: c.border },
  hero: { height: 200, justifyContent: "flex-end", alignItems: "flex-start", padding: spacing.md },
  heroBg: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  glyph: { fontSize: 30, width: 56, height: 56, borderRadius: 28, textAlign: "center", lineHeight: 54, overflow: "hidden", backgroundColor: "rgba(255,255,255,0.92)" },
  body: { padding: spacing.md, marginTop: -spacing.lg },
  regionBadge: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", backgroundColor: c.brandPrimary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  regionTxt: { color: c.onBrandPrimary, fontSize: 12, fontWeight: "700", fontFamily: fonts.body },
  title: { color: c.onSurface, fontSize: 30, fontFamily: fonts.heading, marginTop: spacing.sm, lineHeight: 34 },
  sectionHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  sectionTitle: { color: c.onSurface, fontSize: 18, fontFamily: fonts.heading },
  desc: { color: c.onSurfaceSecondary, fontSize: 15, lineHeight: 23, fontFamily: fonts.body, marginTop: spacing.sm },
  ingRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: c.brand },
  ingTxt: { color: c.onSurfaceSecondary, fontSize: 15, fontFamily: fonts.body },
  funCard: { marginTop: spacing.md, backgroundColor: c.surfaceInverse, borderRadius: radius.lg, padding: spacing.lg, gap: 6 },
  funLabel: { color: c.brand, fontSize: 14, fontWeight: "700", fontFamily: fonts.body },
  funTxt: { color: c.onSurfaceInverse, fontSize: 15, lineHeight: 22, fontStyle: "italic", fontFamily: fonts.body },
}));
