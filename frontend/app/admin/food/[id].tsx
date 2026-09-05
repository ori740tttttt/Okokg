import React, { useEffect, useState } from "react";
import { View, Text, Pressable } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import * as ImagePicker from "expo-image-picker";
import { Linking } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Button, Card, Field, Loading, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";
import { useDishes } from "@/src/lib/dishes";
import { foodCategories } from "@/src/lib/culinary";

export default function AdminDishEditor() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const dishes = useDishes();
  const dish = dishes.data?.find((d) => d.id === id);

  const [name, setName] = useState("");
  const [region, setRegion] = useState("");
  const [category, setCategory] = useState("Palermo");
  const [icon, setIcon] = useState("🍽️");
  const [description, setDescription] = useState("");
  const [ingredients, setIngredients] = useState("");
  const [funFact, setFunFact] = useState("");
  const [image, setImage] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  useEffect(() => {
    if (dish && !ready) {
      setName(dish.name);
      setRegion(dish.region);
      setCategory(dish.category);
      setIcon(dish.icon);
      setDescription(dish.description);
      setIngredients((dish.ingredients ?? []).join("\n"));
      setFunFact(dish.funFact);
      setImage(dish.image ?? "");
      setReady(true);
    }
  }, [dish, ready]);

  const save = useMutation({
    mutationFn: async () =>
      api.put(`/dishes/${id}`, {
        name,
        region,
        category,
        icon,
        description,
        ingredients: ingredients.split("\n").map((x) => x.trim()).filter(Boolean),
        funFact,
        image: image || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dishes"] });
      toast.show("Piatto salvato", "success");
      router.back();
    },
    onError: () => toast.show("Errore salvataggio", "error"),
  });

  const reset = useMutation({
    mutationFn: async () => api.delete(`/dishes/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dishes"] });
      toast.show(dish?.custom ? "Piatto eliminato" : "Ripristinato all'originale", "info");
      router.back();
    },
    onError: () => toast.show("Errore", "error"),
  });

  const pickPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      if (!perm.canAskAgain) {
        toast.show("Attiva l'accesso alle foto dalle Impostazioni", "error");
        Linking.openSettings().catch(() => {});
      } else {
        toast.show("Permesso foto negato", "error");
      }
      return;
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.5,
      base64: true,
      allowsEditing: true,
      aspect: [4, 3],
    });
    if (!res.canceled && res.assets?.[0]?.base64) {
      setImage(`data:image/jpeg;base64,${res.assets[0].base64}`);
    }
  };

  if (loading || !token || (!ready && dish)) return <Loading />;
  if (!dish) return <Loading />;

  return (
    <View style={s.screen}>
      <Header title="Modifica piatto" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl, gap: spacing.md }} bottomOffset={24} showsVerticalScrollIndicator={false}>
        {/* Photo */}
        <Card style={{ alignItems: "center", gap: spacing.sm }}>
          <View style={s.preview}>
            {image ? <Image source={{ uri: image }} style={s.previewImg} contentFit="cover" /> : <Text style={s.previewGlyph}>{icon}</Text>}
          </View>
          <View style={s.photoBtns}>
            <Button testID="pick-photo" label="Scegli foto" icon="image-plus" variant="olive" small onPress={pickPhoto} />
            {image ? <Button testID="remove-photo" label="Rimuovi" icon="close" variant="outline" small onPress={() => setImage("")} /> : null}
          </View>
          <Field value={image} onChangeText={setImage} placeholder="oppure incolla un URL foto" icon="link-variant" autoCapitalize="none" testID="image-url" />
        </Card>

        <Field value={icon} onChangeText={setIcon} placeholder="Icona (emoji)" icon="emoticon-outline" testID="dish-icon" />
        <Field value={name} onChangeText={setName} placeholder="Nome del piatto" icon="silverware-fork-knife" testID="dish-name" />
        <Field value={region} onChangeText={setRegion} placeholder="Zona / Comune" icon="map-marker-outline" testID="dish-region" />

        <View>
          <Text style={s.label}>Categoria</Text>
          <View style={s.cats}>
            {foodCategories.filter((c) => c !== "All").map((c) => (
              <Pressable
                key={c}
                testID={`cat-${c}`}
                onPress={() => setCategory(c)}
                style={[s.cat, { backgroundColor: category === c ? colors.brandPrimary : colors.surfaceTertiary, borderColor: category === c ? colors.brandPrimary : colors.border }]}
              >
                <Text style={[s.catTxt, { color: category === c ? colors.onBrandPrimary : colors.onSurfaceTertiary }]}>{c}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <Field value={description} onChangeText={setDescription} placeholder="Descrizione" icon="text" multiline testID="dish-desc" />
        <View>
          <Text style={s.label}>Ingredienti (uno per riga)</Text>
          <Field value={ingredients} onChangeText={setIngredients} placeholder={"Riso\nZafferano\n..."} icon="format-list-bulleted" multiline testID="dish-ingredients" />
        </View>
        <Field value={funFact} onChangeText={setFunFact} placeholder="Curiosità per il turista" icon="lightbulb-on-outline" multiline testID="dish-funfact" />

        <Button testID="save-dish" label="Salva piatto" icon="content-save" onPress={() => save.mutate()} loading={save.isPending} />
        <Button
          testID="reset-dish"
          label={dish.custom ? "Elimina piatto" : "Ripristina originale"}
          icon="restore"
          variant="outline"
          onPress={() => reset.mutate()}
          loading={reset.isPending}
        />
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  preview: { width: 140, height: 105, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  previewImg: { width: "100%", height: "100%" },
  previewGlyph: { fontSize: 52 },
  photoBtns: { flexDirection: "row", gap: spacing.sm },
  label: { color: c.onSurfaceSecondary, fontSize: 13, fontWeight: "600", fontFamily: fonts.body, marginBottom: spacing.sm },
  cats: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  cat: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1 },
  catTxt: { fontSize: 12, fontWeight: "600", fontFamily: fonts.body },
}));
