import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, Modal, Switch, RefreshControl } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, Loading, EmptyState, ChipRow, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

type Faq = { id: string; category: string; question_it: string; answer_it: string; priority?: number; published?: boolean };

export default function AdminFaqs() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [editing, setEditing] = useState<Partial<Faq> | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const faqs = useQuery({
    queryKey: ["admin-faqs"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/faqs")).data,
  });

  const categories: string[] = faqs.data?.categories ?? ["generale", "casa", "checkin", "dintorni"];

  const save = async () => {
    if (!editing?.question_it?.trim()) return toast.show("Scrivi la domanda", "error");
    setBusy(true);
    const payload = {
      category: editing.category || categories[0],
      question_it: editing.question_it,
      answer_it: editing.answer_it || "",
      keywords: [],
      priority: editing.priority ?? 50,
      published: editing.published ?? true,
    };
    try {
      if (editing.id) await api.put(`/admin/faqs/${editing.id}`, payload);
      else await api.post("/admin/faqs", payload);
      toast.show("FAQ salvata", "success");
      qc.invalidateQueries({ queryKey: ["admin-faqs"] });
      qc.invalidateQueries({ queryKey: ["faqs"] });
      setEditing(null);
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/faqs/${id}`);
      qc.invalidateQueries({ queryKey: ["admin-faqs"] });
      qc.invalidateQueries({ queryKey: ["faqs"] });
      toast.show("Eliminata", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  if (loading || !token) return <Loading />;
  const list: Faq[] = faqs.data?.faqs ?? [];

  return (
    <View style={s.screen}>
      <Header
        title="FAQ"
        kicker="Admin"
        showBack
        showLang={false}
        right={
          <Pressable testID="faq-add" onPress={() => setEditing({ category: categories[0], published: true, priority: 50 })} hitSlop={6} style={s.addBtn}>
            <Icon name="plus" size={22} color={colors.onBrandPrimary} />
          </Pressable>
        }
      />
      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["admin-faqs"] })} tintColor={colors.brandPrimary} />}
      >
        {faqs.isLoading ? (
          <Loading />
        ) : list.length === 0 ? (
          <EmptyState icon="frequently-asked-questions" title="Nessuna FAQ" subtitle="Tocca + per aggiungere la prima." />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {list.map((it) => (
              <Card key={it.id} testID={`faq-${it.id}`} style={{ gap: 4 }}>
                <View style={s.faqHead}>
                  <Text style={s.faqCat}>{it.category?.toUpperCase()}</Text>
                  {!it.published ? <Text style={s.draft}>bozza</Text> : null}
                </View>
                <Text style={s.faqQ}>{it.question_it}</Text>
                <Text style={s.faqA} numberOfLines={3}>{it.answer_it}</Text>
                <View style={s.actions}>
                  <Pressable testID={`faq-edit-${it.id}`} style={s.actBtn} onPress={() => setEditing(it)}>
                    <Icon name="pencil-outline" size={16} color={colors.brandPrimary} />
                    <Text style={s.actTxt}>Modifica</Text>
                  </Pressable>
                  <Pressable testID={`faq-del-${it.id}`} style={s.actBtn} onPress={() => remove(it.id)}>
                    <Icon name="trash-can-outline" size={16} color={colors.error} />
                    <Text style={[s.actTxt, { color: colors.error }]}>Elimina</Text>
                  </Pressable>
                </View>
              </Card>
            ))}
          </View>
        )}
      </ScrollView>

      <Modal visible={!!editing} transparent animationType="slide" onRequestClose={() => setEditing(null)}>
        <Pressable style={s.backdrop} onPress={() => setEditing(null)}>
          <Pressable style={s.sheet} onPress={(e) => e.stopPropagation()}>
            <KeyboardAwareScrollView bottomOffset={20} showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
              <Text style={s.sheetTitle}>{editing?.id ? "Modifica FAQ" : "Nuova FAQ"}</Text>
              <Text style={s.miniLabel}>CATEGORIA</Text>
              <ChipRow items={categories.map((cc) => ({ key: cc, label: cc }))} selected={editing?.category || categories[0]} onSelect={(k) => setEditing((e) => ({ ...e, category: k }))} />
              <Field value={editing?.question_it || ""} onChangeText={(v) => setEditing((e) => ({ ...e, question_it: v }))} placeholder="Domanda" icon="help-circle-outline" multiline testID="faq-q" />
              <Field value={editing?.answer_it || ""} onChangeText={(v) => setEditing((e) => ({ ...e, answer_it: v }))} placeholder="Risposta" icon="reply" multiline testID="faq-a" />
              <View style={s.switchRow}>
                <Text style={s.switchLabel}>Pubblicata</Text>
                <Switch value={editing?.published ?? true} onValueChange={(v) => setEditing((e) => ({ ...e, published: v }))} trackColor={{ true: colors.brandPrimary }} testID="faq-published" />
              </View>
              <Button testID="faq-save" label="Salva" icon="content-save" onPress={save} loading={busy} />
            </KeyboardAwareScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  addBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  faqHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  faqCat: { color: c.brand, fontSize: 11, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body },
  draft: { color: c.warning, fontSize: 11, fontFamily: fonts.body },
  faqQ: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  faqA: { color: c.muted, fontSize: 13, fontFamily: fonts.body, lineHeight: 19 },
  actions: { flexDirection: "row", gap: spacing.md, marginTop: 4, borderTopWidth: 1, borderTopColor: c.divider, paddingTop: 8 },
  actBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  actTxt: { color: c.brandPrimary, fontSize: 13, fontFamily: fonts.body, fontWeight: "600" },
  backdrop: { flex: 1, backgroundColor: "rgba(44,42,40,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, maxHeight: "88%" },
  sheetTitle: { color: c.onSurface, fontSize: 20, fontFamily: fonts.heading, marginBottom: 4 },
  miniLabel: { color: c.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 4 },
  switchLabel: { color: c.onSurface, fontSize: 15, fontFamily: fonts.body },
}));
