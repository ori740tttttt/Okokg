import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, Modal, RefreshControl } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, Loading, EmptyState, ChipRow, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

type GQ = { id: string; name: string; contact: string; message: string; status: string; created_at?: string; answer?: string };

export default function AdminQuestions() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [promote, setPromote] = useState<GQ | null>(null);
  const [cat, setCat] = useState("generale");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const q = useQuery({
    queryKey: ["guest-questions"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/guest-questions")).data,
  });

  const setStatus = async (id: string, status: string) => {
    try {
      await api.patch(`/admin/guest-questions/${id}`, { status });
      qc.invalidateQueries({ queryKey: ["guest-questions"] });
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/guest-questions/${id}`);
      qc.invalidateQueries({ queryKey: ["guest-questions"] });
      toast.show("Eliminata", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  const doPromote = async () => {
    if (!promote) return;
    if (!answer.trim()) return toast.show("Scrivi una risposta", "error");
    setBusy(true);
    try {
      await api.post(`/admin/guest-questions/${promote.id}/promote-to-faq`, {
        category: cat,
        question_it: promote.message,
        answer_it: answer.trim(),
        publish: true,
      });
      await api.patch(`/admin/guest-questions/${promote.id}`, { status: "answered", answer: answer.trim() });
      toast.show("Aggiunta alle FAQ", "success");
      qc.invalidateQueries({ queryKey: ["guest-questions"] });
      qc.invalidateQueries({ queryKey: ["admin-faqs"] });
      setPromote(null); setAnswer("");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !token) return <Loading />;
  const list: GQ[] = q.data?.questions ?? [];
  const counts = q.data?.counts ?? {};

  return (
    <View style={s.screen}>
      <Header title="Domande ospiti" kicker="Admin" showBack showLang={false} />
      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["guest-questions"] })} tintColor={colors.brandPrimary} />}
      >
        <View style={s.countRow}>
          <Text style={s.count}><Text style={{ color: colors.warning }}>●</Text> {counts.open ?? 0} aperte</Text>
          <Text style={s.count}><Text style={{ color: colors.success }}>●</Text> {counts.answered ?? 0} risposte</Text>
          <Text style={s.count}><Text style={{ color: colors.muted }}>●</Text> {counts.closed ?? 0} chiuse</Text>
        </View>

        {q.isLoading ? (
          <Loading />
        ) : list.length === 0 ? (
          <EmptyState icon="comment-question-outline" title="Nessuna domanda" subtitle="Le domande degli ospiti compaiono qui." />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {list.map((it) => (
              <Card key={it.id} testID={`gq-${it.id}`} style={{ gap: 6 }}>
                <View style={s.qHead}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.qName}>{it.name}</Text>
                    <Text style={s.qContact}>{it.contact}</Text>
                  </View>
                  <View style={[s.statusPill, { backgroundColor: (it.status === "open" ? colors.warning : it.status === "answered" ? colors.success : colors.muted) + "22" }]}>
                    <Text style={[s.statusTxt, { color: it.status === "open" ? colors.warning : it.status === "answered" ? colors.success : colors.muted }]}>
                      {it.status === "open" ? "Aperta" : it.status === "answered" ? "Risposta" : "Chiusa"}
                    </Text>
                  </View>
                </View>
                <Text style={s.qMsg}>{it.message}</Text>
                <View style={s.actions}>
                  <Pressable testID={`gq-promote-${it.id}`} style={s.actBtn} onPress={() => { setPromote(it); setAnswer(it.answer || ""); }}>
                    <Icon name="frequently-asked-questions" size={16} color={colors.brandPrimary} />
                    <Text style={s.actTxt}>A FAQ</Text>
                  </Pressable>
                  <Pressable testID={`gq-close-${it.id}`} style={s.actBtn} onPress={() => setStatus(it.id, "closed")}>
                    <Icon name="check" size={16} color={colors.olive} />
                    <Text style={[s.actTxt, { color: colors.olive }]}>Chiudi</Text>
                  </Pressable>
                  <Pressable testID={`gq-del-${it.id}`} style={s.actBtn} onPress={() => remove(it.id)}>
                    <Icon name="trash-can-outline" size={16} color={colors.error} />
                    <Text style={[s.actTxt, { color: colors.error }]}>Elimina</Text>
                  </Pressable>
                </View>
              </Card>
            ))}
          </View>
        )}
      </ScrollView>

      <Modal visible={!!promote} transparent animationType="slide" onRequestClose={() => setPromote(null)}>
        <Pressable style={s.backdrop} onPress={() => setPromote(null)}>
          <Pressable style={s.sheet} onPress={(e) => e.stopPropagation()}>
            <Text style={s.sheetTitle}>Aggiungi alle FAQ</Text>
            <Text style={s.sheetQ}>{promote?.message}</Text>
            <Text style={s.miniLabel}>CATEGORIA</Text>
            <ChipRow
              items={[
                { key: "generale", label: "Generale" },
                { key: "casa", label: "Casa" },
                { key: "checkin", label: "Check-in" },
                { key: "dintorni", label: "Dintorni" },
              ]}
              selected={cat}
              onSelect={setCat}
            />
            <Field value={answer} onChangeText={setAnswer} placeholder="Risposta ufficiale" icon="reply" multiline testID="gq-answer" />
            <Button testID="gq-promote-submit" label="Pubblica FAQ" icon="check" onPress={doPromote} loading={busy} />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  countRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.md },
  count: { color: c.onSurface, fontSize: 13, fontFamily: fonts.body },
  qHead: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  qName: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  qContact: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginTop: 1 },
  statusPill: { borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 3 },
  statusTxt: { fontSize: 11, fontFamily: fonts.body, fontWeight: "700" },
  qMsg: { color: c.onSurface, fontSize: 14, fontFamily: fonts.body, lineHeight: 20 },
  actions: { flexDirection: "row", gap: spacing.md, marginTop: 4, borderTopWidth: 1, borderTopColor: c.divider, paddingTop: 8 },
  actBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  actTxt: { color: c.brandPrimary, fontSize: 13, fontFamily: fonts.body, fontWeight: "600" },
  backdrop: { flex: 1, backgroundColor: "rgba(44,42,40,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  sheetTitle: { color: c.onSurface, fontSize: 20, fontFamily: fonts.heading },
  sheetQ: { color: c.muted, fontSize: 14, fontFamily: fonts.body, fontStyle: "italic" },
  miniLabel: { color: c.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body, marginTop: 4 },
}));
