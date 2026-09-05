import React, { useEffect, useState } from "react";
import { View, Text } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, useToast } from "@/src/components/ui";
import { makeStyles } from "@/src/theme";
import { fonts, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

export default function AdminCommissions() {
  const s = useStyles();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [state, setState] = useState("");
  const [booking, setBooking] = useState("");
  const [vat, setVat] = useState("");
  const [bank, setBank] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const rates = useQuery({
    queryKey: ["commission-rates"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/commission-rates")).data,
  });

  useEffect(() => {
    const d = rates.data;
    if (d) {
      setState(String(d.state_pct ?? ""));
      setBooking(String(d.booking_pct ?? ""));
      setVat(String(d.vat_pct ?? ""));
      setBank(String(d.bank_pct ?? ""));
    }
  }, [rates.data]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/commission-rates", {
        state_pct: parseFloat(state) || 0,
        booking_pct: parseFloat(booking) || 0,
        vat_pct: parseFloat(vat) || 0,
        bank_pct: parseFloat(bank) || 0,
      });
      toast.show("Tariffe aggiornate", "success");
      qc.invalidateQueries({ queryKey: ["commission-rates"] });
      qc.invalidateQueries({ queryKey: ["admin-accounting"] });
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !token) return <Loading />;

  return (
    <View style={s.screen}>
      <Header title="Costi & tariffe" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        {rates.isLoading ? (
          <Loading />
        ) : (
          <Card style={{ gap: spacing.sm }}>
            <SectionTitle kicker="Booking.com" title="Trattenute in %" />
            <Text style={s.hint}>Applicate solo alle vendite Booking.com per calcolare il netto in Contabilità.</Text>
            <Field value={state} onChangeText={setState} placeholder="Tassa di Stato (%)" icon="bank-outline" keyboardType="numeric" testID="cr-state" />
            <Field value={booking} onChangeText={setBooking} placeholder="Commissione Booking (%)" icon="alpha-b-box" keyboardType="numeric" testID="cr-booking" />
            <Field value={vat} onChangeText={setVat} placeholder="IVA (%)" icon="receipt-text-outline" keyboardType="numeric" testID="cr-vat" />
            <Field value={bank} onChangeText={setBank} placeholder="Banca / transazioni (%)" icon="credit-card-outline" keyboardType="numeric" testID="cr-bank" />
            <View style={{ marginTop: spacing.md }}>
              <Button testID="cr-save" label="Salva tariffe" icon="content-save" onPress={save} loading={saving} />
            </View>
          </Card>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  hint: { color: c.muted, fontSize: 13, fontFamily: fonts.body, marginBottom: spacing.xs },
}));
