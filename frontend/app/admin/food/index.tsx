import React, { useEffect } from "react";
import { View, Text, FlatList, Pressable } from "react-native";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Loading, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";
import { useDishes, MergedDish } from "@/src/lib/dishes";

export default function AdminFood() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const dishes = useDishes();

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const create = useMutation({
    mutationFn: async () => (await api.post("/dishes", { name: "Nuovo piatto", category: "Palermo", icon: "🍽️" })).data,
    onSuccess: (d: { id: string }) => {
      qc.invalidateQueries({ queryKey: ["dishes"] });
      router.push({ pathname: "/admin/food/[id]", params: { id: d.id } });
    },
    onError: () => toast.show("Errore creazione", "error"),
  });

  if (loading || !token) return <Loading />;

  const renderItem = ({ item }: { item: MergedDish }) => (
    <Pressable
      testID={`admin-dish-${item.id}`}
      style={s.row}
      onPress={() => router.push({ pathname: "/admin/food/[id]", params: { id: item.id } })}
    >
      <View style={s.thumb}>
        {item.image ? <Image source={{ uri: item.image }} style={s.thumbImg} contentFit="cover" /> : <Text style={s.glyph}>{item.icon}</Text>}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.name} numberOfLines={1}>{item.name || "—"}</Text>
        <Text style={s.meta} numberOfLines={1}>{item.category}{item.custom ? " · custom" : ""}</Text>
      </View>
      <Icon name="pencil" size={20} color={colors.brandPrimary} />
    </Pressable>
  );

  return (
    <View style={s.screen}>
      <Header
        title="Cucina · Gestione"
        kicker="Admin"
        showBack
        showLang={false}
        right={
          <Pressable testID="add-dish" onPress={() => create.mutate()} style={s.addBtn} hitSlop={6}>
            <Icon name="plus" size={22} color={colors.onBrandPrimary} />
          </Pressable>
        }
      />
      {dishes.isLoading ? (
        <Loading />
      ) : (
        <FlatList
          testID="admin-food-list"
          data={dishes.data ?? []}
          keyExtractor={(d) => d.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: spacing.md, gap: spacing.sm, paddingBottom: spacing.xxl }}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={<Text style={s.hint}>Tocca un piatto per modificare foto, ingredienti e curiosità. Usa + per aggiungerne uno nuovo.</Text>}
        />
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  addBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  hint: { color: c.muted, fontSize: 13, marginBottom: spacing.sm, fontFamily: fonts.body },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: spacing.sm },
  thumb: { width: 52, height: 52, borderRadius: radius.sm, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  thumbImg: { width: "100%", height: "100%" },
  glyph: { fontSize: 26 },
  name: { color: c.onSurface, fontSize: 16, fontFamily: fonts.heading },
  meta: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginTop: 2 },
}));
