import React, { useEffect, useState } from "react";
import { View, Text, Pressable, Switch } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, ChipRow, EmptyState, useToast } from "@/src/components/ui";
import { DateField } from "@/src/components/DateField";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

const today = () => new Date().toISOString().slice(0, 10);
const inOneYear = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
};

export default function AdminDiscounts() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [code, setCode] = useState("");
  const [type, setType] = useState("discount");
  const [percent, setPercent] = useState("");
  const [from, setFrom] = useState(today());
  const [to, setTo] = useState(inOneYear());
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const codes = useQuery({
    queryKey: ["discount-codes"],
    enabled: !!token,
    queryFn: async () => (await api.get("/discount-codes")).data as any[],
  });

  const create = async () => {
    if (!code.trim()) return toast.show("Inserisci un codice", "error");
    if (type === "discount" && (!percent || parseFloat(percent) <= 0)) return toast.show("Percentuale obbligatoria", "error");
    setSaving(true);
    try {
      await api.post("/discount-codes", {
        code: code.trim().toUpperCase(),
        type,
        percent: type === "discount" ? parseFloat(percent) : null,
        valid_from: from,
        valid_to: to,
        active,
      });
      toast.show("Codice creato", "success");
      qc.invalidateQueries({ queryKey: ["discount-codes"] });
      setCode(""); setPercent("");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/discount-codes/${id}`);
      qc.invalidateQueries({ queryKey: ["discount-codes"] });
      toast.show("Codice eliminato", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  if (loading || !token) return <Loading />;
  const list = codes.data ?? [];

  return (
    <View style={s.screen}>
      <Header title="Codici sconto" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        <Card style={{ gap: spacing.sm }}>
          <SectionTitle title="Nuovo codice" />
          <Field value={code} onChangeText={setCode} placeholder="Codice (es. ESTATE10)" icon="ticket-percent-outline" autoCapitalize="characters" testID="dc-code" />
          <ChipRow
            items={[{ key: "discount", label: "Sconto %", icon: "sale" }, { key: "ai_access", label: "Sblocco mappa/IA", icon: "key-variant" }]}
            selected={type}
            onSelect={setType}
          />
          {type === "discount" ? (
            <Field value={percent} onChangeText={setPercent} placeholder="Percentuale sconto (%)" icon="percent-outline" keyboardType="numeric" testID="dc-percent" />
          ) : null}
          <View style={s.dateRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.miniLabel}>DAL</Text>
              <DateField value={from} onChange={setFrom} testID="dc-from" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.miniLabel}>AL</Text>
              <DateField value={to} onChange={setTo} minDate={from} testID="dc-to" />
            </View>
          </View>
          <View style={s.switchRow}>
            <Text style={s.switchLabel}>Attivo</Text>
            <Switch value={active} onValueChange={setActive} trackColor={{ true: colors.brandPrimary }} testID="dc-active" />
          </View>
          <Button testID="dc-create" label="Crea codice" icon="plus" onPress={create} loading={saving} />
        </Card>

        <SectionTitle title={`Codici attivi (${list.length})`} />
        {codes.isLoading ? (
          <Loading />
        ) : list.length === 0 ? (
          <EmptyState icon="ticket-outline" title="Nessun codice" subtitle="Crea il primo codice qui sopra." />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {list.map((it) => (
              <Card key={it.id} style={s.item} testID={`dc-item-${it.code}`}>
                <View style={[s.tIcon, { backgroundColor: (it.type === "ai_access" ? colors.olive : colors.brandPrimary) + "22" }]}>
                  <Icon name={it.type === "ai_access" ? "key-variant" : "sale"} size={20} color={it.type === "ai_access" ? colors.olive : colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.code}>{it.code}</Text>
                  <Text style={s.meta}>
                    {it.type === "ai_access" ? "Sblocco mappa/IA" : `Sconto ${it.percent}%`} · {it.valid_from} → {it.valid_to}
                  </Text>
                  {!it.active ? <Text style={s.inactive}>disattivato</Text> : null}
                </View>
                <Pressable testID={`dc-del-${it.code}`} onPress={() => remove(it.id)} hitSlop={8} style={s.del}>
                  <Icon name="trash-can-outline" size={20} color={colors.error} />
                </Pressable>
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
  dateRow: { flexDirection: "row", gap: spacing.sm },
  miniLabel: { color: c.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body, marginBottom: 4 },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 4 },
  switchLabel: { color: c.onSurface, fontSize: 15, fontFamily: fonts.body },
  item: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  tIcon: { width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  code: { color: c.onSurface, fontSize: 17, fontFamily: fonts.heading, letterSpacing: 1 },
  meta: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginTop: 2 },
  inactive: { color: c.error, fontSize: 11, fontFamily: fonts.body, marginTop: 2 },
  del: { padding: 6 },
}));
