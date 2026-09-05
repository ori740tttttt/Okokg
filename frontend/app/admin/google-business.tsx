import React, { useEffect, useState } from "react";
import { View, Text, Pressable } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import * as Clipboard from "expo-clipboard";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, ChipRow, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

export default function AdminGoogleBusiness() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [bizName, setBizName] = useState("");
  const [reviewLink, setReviewLink] = useState("");
  const [mapsUrl, setMapsUrl] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);

  const [postType, setPostType] = useState("update");
  const [topic, setTopic] = useState("");
  const [post, setPost] = useState<any>(null);
  const [genPost, setGenPost] = useState(false);

  const [review, setReview] = useState("");
  const [reply, setReply] = useState("");
  const [genReply, setGenReply] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const settings = useQuery({
    queryKey: ["gb-settings"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/google-business/settings")).data,
  });

  useEffect(() => {
    const d = settings.data;
    if (d) {
      setBizName(d.business_name || "");
      setReviewLink(d.review_link || "");
      setMapsUrl(d.maps_url || "");
    }
  }, [settings.data]);

  const saveSettings = async () => {
    setSavingSettings(true);
    try {
      await api.put("/admin/google-business/settings", { business_name: bizName, review_link: reviewLink, maps_url: mapsUrl });
      toast.show("Impostazioni salvate", "success");
      qc.invalidateQueries({ queryKey: ["gb-settings"] });
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setSavingSettings(false);
    }
  };

  const generatePost = async () => {
    if (topic.trim().length < 3) return toast.show("Indica l'argomento del post", "error");
    setGenPost(true); setPost(null);
    try {
      const res = await api.post("/admin/google-business/post", { post_type: postType, topic: topic.trim(), languages: ["it"] });
      setPost(res.data);
      toast.show("Post generato", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore IA", "error");
    } finally {
      setGenPost(false);
    }
  };

  const generateReply = async () => {
    if (review.trim().length < 3) return toast.show("Incolla la recensione", "error");
    setGenReply(true); setReply("");
    try {
      const res = await api.post("/admin/google-business/review-reply", { review_text: review.trim() });
      setReply(res.data?.reply || "");
      toast.show("Risposta generata", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore IA", "error");
    } finally {
      setGenReply(false);
    }
  };

  const copy = async (txt: string) => {
    await Clipboard.setStringAsync(txt);
    toast.show("Copiato negli appunti", "success");
  };

  if (loading || !token) return <Loading />;
  const postIt = post?.content?.it;
  const postText = postIt ? [postIt.summary, postIt.cta_button ? `👉 ${postIt.cta_button}` : ""].filter(Boolean).join("\n\n") : "";

  return (
    <View style={s.screen}>
      <Header title="Google Business" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        {settings.isLoading ? (
          <Loading />
        ) : (
          <>
            <Card style={{ gap: spacing.sm }}>
              <SectionTitle title="Profilo" />
              <Field value={bizName} onChangeText={setBizName} placeholder="Nome attività" icon="storefront-outline" testID="gb-name" />
              <Field value={reviewLink} onChangeText={setReviewLink} placeholder="Link recensioni Google" icon="link-variant" autoCapitalize="none" testID="gb-reviewlink" />
              <Field value={mapsUrl} onChangeText={setMapsUrl} placeholder="Link Google Maps" icon="map-outline" autoCapitalize="none" testID="gb-mapsurl" />
              <Button testID="gb-save-settings" label="Salva profilo" icon="content-save" onPress={saveSettings} loading={savingSettings} />
            </Card>

            <SectionTitle title="Genera un post GBP" />
            <Card style={{ gap: spacing.sm }}>
              <Text style={s.miniLabel}>TIPO</Text>
              <ChipRow
                items={[{ key: "update", label: "Novità", icon: "bullhorn-outline" }, { key: "offer", label: "Offerta", icon: "sale" }, { key: "event", label: "Evento", icon: "calendar-star" }]}
                selected={postType}
                onSelect={setPostType}
              />
              <Field value={topic} onChangeText={setTopic} placeholder="Argomento (es. offerta weekend settembre)" icon="lightbulb-outline" multiline testID="gb-topic" />
              <Button testID="gb-gen-post" label="Genera post con Carmelo" icon="creation" onPress={generatePost} loading={genPost} />
              {postText ? (
                <View style={s.result} testID="gb-post-result">
                  <View style={s.resHead}>
                    <Text style={s.resTitle}>Post pronto</Text>
                    <Pressable testID="gb-copy-post" onPress={() => copy(postText)} hitSlop={6}><Icon name="content-copy" size={20} color={colors.brandPrimary} /></Pressable>
                  </View>
                  <Text style={s.resBody}>{postText}</Text>
                  {post?.image_idea ? <Text style={s.resExtra}>📸 {post.image_idea}</Text> : null}
                </View>
              ) : null}
            </Card>

            <SectionTitle title="Rispondi a una recensione" />
            <Card style={{ gap: spacing.sm }}>
              <Field value={review} onChangeText={setReview} placeholder="Incolla qui la recensione dell'ospite" icon="comment-quote-outline" multiline testID="gb-review" />
              <Button testID="gb-gen-reply" label="Genera risposta" icon="reply" variant="olive" onPress={generateReply} loading={genReply} />
              {reply ? (
                <View style={s.result} testID="gb-reply-result">
                  <View style={s.resHead}>
                    <Text style={s.resTitle}>Risposta suggerita</Text>
                    <Pressable testID="gb-copy-reply" onPress={() => copy(reply)} hitSlop={6}><Icon name="content-copy" size={20} color={colors.brandPrimary} /></Pressable>
                  </View>
                  <Text style={s.resBody}>{reply}</Text>
                </View>
              ) : null}
            </Card>
          </>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  miniLabel: { color: c.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body },
  result: { backgroundColor: c.surfaceTertiary, borderRadius: radius.md, padding: spacing.md, gap: 6, marginTop: 4 },
  resHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  resTitle: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  resBody: { color: c.onSurface, fontSize: 14, fontFamily: fonts.body, lineHeight: 21 },
  resExtra: { color: c.muted, fontSize: 13, fontFamily: fonts.body },
}));
