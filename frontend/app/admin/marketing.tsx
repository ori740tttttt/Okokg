import React, { useEffect, useState } from "react";
import { View, Text, Pressable, RefreshControl } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import * as Clipboard from "expo-clipboard";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, EmptyState, ChipRow, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

const PLATFORMS = [
  { key: "instagram_post", label: "Instagram", icon: "instagram" as const },
  { key: "facebook_post", label: "Facebook", icon: "facebook" as const },
  { key: "google_business", label: "Google", icon: "google" as const },
  { key: "tiktok", label: "TikTok", icon: "music-note" as const },
  { key: "x_twitter", label: "X", icon: "alpha-x-box" as const },
];

function renderContent(content: any): string {
  if (!content) return "";
  if (typeof content === "string") return content;
  const parts: string[] = [];
  for (const [k, v] of Object.entries(content)) {
    const val = Array.isArray(v) ? v.map((x) => (k.toLowerCase().includes("hashtag") ? `#${x}` : x)).join(" ") : typeof v === "object" ? renderContent(v) : String(v);
    parts.push(val);
  }
  return parts.join("\n\n");
}

export default function AdminMarketing() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [platform, setPlatform] = useState("instagram_post");
  const [topic, setTopic] = useState("");
  const [tone, setTone] = useState("");
  const [result, setResult] = useState<any>(null);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const library = useQuery({
    queryKey: ["marketing-library"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/marketing/library")).data as any[],
  });

  const generate = async () => {
    if (topic.trim().length < 3) return toast.show("Indica un argomento", "error");
    setGenerating(true);
    setResult(null);
    try {
      const res = await api.post("/admin/marketing/generate", {
        platform,
        topic: topic.trim(),
        tone: tone.trim() || null,
        languages: ["it"],
      });
      setResult(res.data);
      qc.invalidateQueries({ queryKey: ["marketing-library"] });
      toast.show("Contenuto generato", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore IA", "error");
    } finally {
      setGenerating(false);
    }
  };

  const copy = async (item: any) => {
    await Clipboard.setStringAsync(renderContent(item.content));
    toast.show("Copiato negli appunti", "success");
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/marketing/library/${id}`);
      qc.invalidateQueries({ queryKey: ["marketing-library"] });
      toast.show("Eliminato", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  if (loading || !token) return <Loading />;
  const lib = library.data ?? [];

  return (
    <View style={s.screen}>
      <Header title="Marketing AI" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        bottomOffset={20}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["marketing-library"] })} tintColor={colors.brandPrimary} />}
      >
        <Card style={{ gap: spacing.sm }}>
          <SectionTitle title="Genera un post" />
          <Text style={s.miniLabel}>PIATTAFORMA</Text>
          <ChipRow items={PLATFORMS} selected={platform} onSelect={setPlatform} />
          <Field value={topic} onChangeText={setTopic} placeholder="Argomento (es. offerta settembre, Cous Cous Fest)" icon="lightbulb-outline" multiline testID="mkt-topic" />
          <Field value={tone} onChangeText={setTone} placeholder="Tono (opzionale: emozionale, ironico...)" icon="palette-outline" testID="mkt-tone" />
          <Button testID="mkt-generate" label="Genera con Carmelo IA" icon="creation" onPress={generate} loading={generating} />
        </Card>

        {result ? (
          <Card style={s.resultCard} testID="mkt-result">
            <View style={s.resHead}>
              <Text style={s.resTitle}>{result.platform_label}</Text>
              <Pressable testID="mkt-copy-result" onPress={() => copy(result)} hitSlop={6}>
                <Icon name="content-copy" size={20} color={colors.brandPrimary} />
              </Pressable>
            </View>
            <Text style={s.resBody}>{renderContent(result.content)}</Text>
            {result.visual_concept ? <Text style={s.resExtra}>📸 {result.visual_concept}</Text> : null}
            {result.best_time ? <Text style={s.resExtra}>⏰ {result.best_time}</Text> : null}
          </Card>
        ) : null}

        <SectionTitle title={`Libreria contenuti (${lib.length})`} />
        {library.isLoading ? (
          <Loading />
        ) : lib.length === 0 ? (
          <EmptyState icon="bullhorn-outline" title="Nessun contenuto" subtitle="Genera il primo post qui sopra." />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {lib.map((it) => (
              <Card key={it.id} testID={`mkt-item-${it.id}`} style={{ gap: 6 }}>
                <View style={s.resHead}>
                  <View style={s.badge}>
                    <Text style={s.badgeTxt}>{it.platform_label}</Text>
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.md }}>
                    <Pressable testID={`mkt-copy-${it.id}`} onPress={() => copy(it)} hitSlop={6}>
                      <Icon name="content-copy" size={18} color={colors.brandPrimary} />
                    </Pressable>
                    <Pressable testID={`mkt-del-${it.id}`} onPress={() => remove(it.id)} hitSlop={6}>
                      <Icon name="trash-can-outline" size={18} color={colors.error} />
                    </Pressable>
                  </View>
                </View>
                <Text style={s.libTopic}>{it.topic}</Text>
                <Text style={s.libBody} numberOfLines={4}>{renderContent(it.content)}</Text>
              </Card>
            ))}
          </View>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  miniLabel: { color: c.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body },
  resultCard: { marginTop: spacing.md, borderColor: c.brandPrimary, borderWidth: 1.5, gap: 6 },
  resHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  resTitle: { color: c.onSurface, fontSize: 16, fontFamily: fonts.heading },
  resBody: { color: c.onSurface, fontSize: 14, fontFamily: fonts.body, lineHeight: 21 },
  resExtra: { color: c.muted, fontSize: 13, fontFamily: fonts.body, marginTop: 2 },
  badge: { backgroundColor: c.surfaceTertiary, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3 },
  badgeTxt: { color: c.onSurfaceTertiary, fontSize: 11, fontFamily: fonts.body, fontWeight: "700" },
  libTopic: { color: c.onSurface, fontSize: 14, fontFamily: fonts.heading },
  libBody: { color: c.muted, fontSize: 13, fontFamily: fonts.body, lineHeight: 19 },
}));
