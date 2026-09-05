import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, RefreshControl, Linking } from "react-native";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Button, Loading, EmptyState, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

type Photo = { id: string; data_url: string; filename?: string };

export default function AdminPhotos() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const photos = useQuery({
    queryKey: ["photos"],
    enabled: !!token,
    queryFn: async () => (await api.get<Photo[]>("/photos")).data,
  });

  const pick = async () => {
    const perm = await ImagePicker.getMediaLibraryPermissionsAsync();
    let status = perm.status;
    if (status !== "granted") {
      if (!perm.canAskAgain) {
        toast.show("Consenti l'accesso alle foto dalle Impostazioni", "error");
        Linking.openSettings();
        return;
      }
      const req = await ImagePicker.requestMediaLibraryPermissionsAsync();
      status = req.status;
      if (status !== "granted") {
        toast.show("Permesso foto negato", "error");
        return;
      }
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.7,
      base64: true,
    });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    const asset = res.assets[0];
    const mime = asset.mimeType || "image/jpeg";
    setUploading(true);
    try {
      await api.post("/photos", {
        data_url: `data:${mime};base64,${asset.base64}`,
        filename: asset.fileName || "foto.jpg",
      });
      toast.show("Foto caricata", "success");
      qc.invalidateQueries({ queryKey: ["photos"] });
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore caricamento", "error");
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/photos/${id}`);
      qc.invalidateQueries({ queryKey: ["photos"] });
      toast.show("Foto eliminata", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  if (loading || !token) return <Loading />;
  const list = photos.data ?? [];

  return (
    <View style={s.screen}>
      <Header title="Foto" kicker="Admin" showBack showLang={false} />
      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["photos"] })} tintColor={colors.brandPrimary} />}
      >
        <Card style={{ marginBottom: spacing.md }}>
          <Text style={s.hint}>Galleria pubblica dell{"'"}appartamento, mostrata agli ospiti in Home.</Text>
          <Button testID="photo-add" label="Carica foto" icon="image-plus" onPress={pick} loading={uploading} />
        </Card>

        {photos.isLoading ? (
          <Loading />
        ) : list.length === 0 ? (
          <EmptyState icon="image-multiple-outline" title="Nessuna foto" subtitle="Carica la prima foto della casa." />
        ) : (
          <View style={s.grid}>
            {list.map((p) => (
              <View key={p.id} style={s.cell} testID={`photo-${p.id}`}>
                <Image source={{ uri: p.data_url }} style={s.img} contentFit="cover" />
                <Pressable testID={`photo-del-${p.id}`} style={s.delBtn} onPress={() => remove(p.id)} hitSlop={6}>
                  <Icon name="close" size={16} color={colors.onError} />
                </Pressable>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  hint: { color: c.muted, fontSize: 13, fontFamily: fonts.body, marginBottom: spacing.sm },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  cell: { width: "31.5%", aspectRatio: 1, borderRadius: radius.md, overflow: "hidden", position: "relative" },
  img: { width: "100%", height: "100%", backgroundColor: c.surfaceTertiary },
  delBtn: { position: "absolute", top: 4, right: 4, width: 26, height: 26, borderRadius: 13, backgroundColor: c.error, alignItems: "center", justifyContent: "center" },
}));
