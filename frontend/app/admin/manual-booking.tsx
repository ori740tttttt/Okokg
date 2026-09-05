import React, { useEffect, useMemo, useState } from "react";
import { View, Text } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, ChipRow, useToast } from "@/src/components/ui";
import { DateField } from "@/src/components/DateField";
import { makeStyles } from "@/src/theme";
import { fonts, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

export default function AdminManualBooking() {
  const s = useStyles();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [guests, setGuests] = useState("2");
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("site");
  const [status, setStatus] = useState("approved");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const nights = useMemo(() => {
    if (!checkIn || !checkOut) return 0;
    const a = new Date(checkIn).getTime();
    const b = new Date(checkOut).getTime();
    return b > a ? Math.round((b - a) / 86400000) : 0;
  }, [checkIn, checkOut]);

  const submit = async () => {
    if (!name.trim()) return toast.show("Inserisci il nome ospite", "error");
    if (!checkIn || !checkOut) return toast.show("Seleziona check-in e check-out", "error");
    if (nights <= 0) return toast.show("Il check-out deve essere dopo il check-in", "error");
    if (!amount) return toast.show("Inserisci l'importo lordo", "error");
    setSaving(true);
    try {
      await api.post("/admin/bookings/manual", {
        guest_name: name.trim(),
        guest_email: email.trim() || "",
        check_in: checkIn,
        check_out: checkOut,
        guests: parseInt(guests, 10) || 1,
        total_amount: parseFloat(amount),
        source,
        status,
      });
      toast.show("Prenotazione inserita", "success");
      qc.invalidateQueries({ queryKey: ["admin-accounting"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
      qc.invalidateQueries({ queryKey: ["admin-bookings"] });
      qc.invalidateQueries({ queryKey: ["availability"] });
      setName(""); setEmail(""); setCheckIn(""); setCheckOut(""); setGuests("2"); setAmount("");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !token) return <Loading />;

  return (
    <View style={s.screen}>
      <Header title="Prenotazione manuale" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        <Card style={{ gap: spacing.sm }}>
          <SectionTitle title="Dati ospite" />
          <Field value={name} onChangeText={setName} placeholder="Nome ospite" icon="account-outline" testID="mb-name" />
          <Field value={email} onChangeText={setEmail} placeholder="Email (opzionale)" icon="email-outline" keyboardType="email-address" autoCapitalize="none" testID="mb-email" />

          <SectionTitle title="Soggiorno" />
          <View style={s.dateRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.miniLabel}>CHECK-IN</Text>
              <DateField value={checkIn} onChange={setCheckIn} placeholder="Arrivo" testID="mb-checkin" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.miniLabel}>CHECK-OUT</Text>
              <DateField value={checkOut} onChange={setCheckOut} placeholder="Partenza" minDate={checkIn || undefined} testID="mb-checkout" />
            </View>
          </View>
          {nights > 0 ? <Text style={s.nights}>{nights} {nights === 1 ? "notte" : "notti"}</Text> : null}
          <Field value={guests} onChangeText={setGuests} placeholder="Ospiti" icon="account-group-outline" keyboardType="numeric" testID="mb-guests" />
          <Field value={amount} onChangeText={setAmount} placeholder="Importo lordo (€)" icon="cash" keyboardType="numeric" testID="mb-amount" />

          <SectionTitle title="Sorgente" />
          <ChipRow
            items={[{ key: "site", label: "Sito", icon: "web" }, { key: "booking", label: "Booking.com", icon: "alpha-b-box" }]}
            selected={source}
            onSelect={setSource}
          />
          <SectionTitle title="Stato" />
          <ChipRow
            items={[{ key: "approved", label: "Approvata", icon: "check" }, { key: "pending", label: "In attesa", icon: "clock-outline" }]}
            selected={status}
            onSelect={setStatus}
          />

          <View style={{ marginTop: spacing.md }}>
            <Button testID="mb-submit" label="Inserisci prenotazione" icon="content-save" onPress={submit} loading={saving} />
          </View>
        </Card>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  dateRow: { flexDirection: "row", gap: spacing.sm },
  miniLabel: { color: c.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700", fontFamily: fonts.body, marginBottom: 4 },
  nights: { color: c.brand, fontSize: 13, fontFamily: fonts.body, fontWeight: "600" },
}));
