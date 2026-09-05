import React, { useEffect, useState } from "react";
import { View, Text, Switch } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, useToast } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

export default function AdminWhatsApp() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [enabled, setEnabled] = useState(false);
  const [phone, setPhone] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySet, setApiKeySet] = useState(false);
  const [nNew, setNNew] = useState(true);
  const [nApproved, setNApproved] = useState(true);
  const [nRejected, setNRejected] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const cfg = useQuery({
    queryKey: ["whatsapp"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/whatsapp")).data,
  });

  useEffect(() => {
    const d = cfg.data;
    if (d) {
      setEnabled(!!d.enabled);
      setPhone(d.phone || "");
      setApiKeySet(!!d.api_key_set);
      setNNew(d.notify_new_request !== false);
      setNApproved(d.notify_approved !== false);
      setNRejected(!!d.notify_rejected);
    }
  }, [cfg.data]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/whatsapp", {
        enabled, phone, api_key: apiKey,
        notify_new_request: nNew, notify_approved: nApproved, notify_rejected: nRejected,
      });
      toast.show("Impostazioni salvate", "success");
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["whatsapp"] });
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    try {
      await api.post("/admin/whatsapp/test", {});
      toast.show("Messaggio di test inviato", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setTesting(false);
    }
  };

  if (loading || !token) return <Loading />;

  const Row = ({ label, value, onValueChange, testID }: { label: string; value: boolean; onValueChange: (v: boolean) => void; testID: string }) => (
    <View style={s.switchRow}>
      <Text style={s.switchLabel}>{label}</Text>
      <Switch value={value} onValueChange={onValueChange} trackColor={{ true: colors.brandPrimary }} testID={testID} />
    </View>
  );

  return (
    <View style={s.screen}>
      <Header title="WhatsApp" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        {cfg.isLoading ? (
          <Loading />
        ) : (
          <>
            <Card style={{ gap: spacing.sm }}>
              <SectionTitle title="Notifiche WhatsApp" />
              <Text style={s.hint}>Ricevi un messaggio WhatsApp quando arriva o cambia una prenotazione (via CallMeBot).</Text>
              <Row label="Abilita notifiche" value={enabled} onValueChange={setEnabled} testID="wa-enabled" />
              <Field value={phone} onChangeText={setPhone} placeholder="Numero (+39...)" icon="phone-outline" keyboardType="phone-pad" testID="wa-phone" />
              <Field
                value={apiKey}
                onChangeText={setApiKey}
                placeholder={apiKeySet ? "API key CallMeBot (già impostata)" : "API key CallMeBot"}
                icon="key-outline"
                autoCapitalize="none"
                testID="wa-apikey"
              />
            </Card>

            <SectionTitle title="Quando notificare" />
            <Card style={{ gap: 2 }}>
              <Row label="Nuova richiesta" value={nNew} onValueChange={setNNew} testID="wa-new" />
              <Row label="Prenotazione approvata" value={nApproved} onValueChange={setNApproved} testID="wa-approved" />
              <Row label="Prenotazione rifiutata" value={nRejected} onValueChange={setNRejected} testID="wa-rejected" />
            </Card>

            <View style={{ marginTop: spacing.lg, gap: spacing.sm }}>
              <Button testID="wa-save" label="Salva impostazioni" icon="content-save" onPress={save} loading={saving} />
              <Button testID="wa-test" label="Invia messaggio di test" icon="send-outline" variant="outline" onPress={test} loading={testing} />
            </View>
          </>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  hint: { color: c.muted, fontSize: 13, fontFamily: fonts.body, marginBottom: spacing.xs },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8 },
  switchLabel: { color: c.onSurface, fontSize: 15, fontFamily: fonts.body },
}));
