import React, { useState } from "react";
import { View, Text, Pressable, ScrollView, LayoutAnimation, Platform, UIManager, Linking } from "react-native";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import Animated, { FadeIn } from "react-native-reanimated";

import { Header } from "@/src/components/Header";
import { Card, EmptyState, Loading, Button, Field, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useFaqs } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import i18n from "@/src/i18n";

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export default function InfoScreen() {
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const faqs = useFaqs(i18n.language);
  const [open, setOpen] = useState<string | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [qName, setQName] = useState("");
  const [qContact, setQContact] = useState("");
  const [qMessage, setQMessage] = useState("");
  const [sending, setSending] = useState(false);

  const toggle = (id: string) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((o) => (o === id ? null : id));
  };

  const sendQuestion = async () => {
    if (!qName.trim() || !qContact.trim() || !qMessage.trim()) {
      return toast.show(t("booking.toast_need_name_email"), "error");
    }
    setSending(true);
    try {
      await api.post("/guest-questions", {
        name: qName,
        contact: qContact,
        contact_kind: qContact.includes("@") ? "email" : "phone",
        message: qMessage,
        language: i18n.language,
      });
      toast.show(t("booking.toast_sent"), "success");
      setQName("");
      setQContact("");
      setQMessage("");
      setAskOpen(false);
    } catch {
      toast.show(t("booking.toast_error"), "error");
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={s.screen}>
      <Header
        title="Info & FAQ"
        kicker="Appartamento Matteo"
        right={
          <Pressable testID="admin-entry" onPress={() => router.push("/admin/login")} style={s.adminBtn} hitSlop={6}>
            <Icon name="shield-account-outline" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>
        }
      />
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} showsVerticalScrollIndicator={false}>
        {/* Guest question CTA */}
        <Card style={{ backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }}>
          <Text style={s.ctaTitle}>{t("map_tutorial.badge")}</Text>
          <Text style={s.ctaDesc}>{t("ai_itinerary.description")}</Text>
          <View style={{ marginTop: spacing.md }}>
            <Button testID="ask-question-btn" label={"Fai una domanda"} icon="chat-question-outline" variant="secondary" onPress={() => setAskOpen((v) => !v)} />
          </View>
          {askOpen ? (
            <Animated.View entering={FadeIn} style={{ gap: spacing.sm, marginTop: spacing.md }}>
              <Field value={qName} onChangeText={setQName} placeholder={t("booking.name_placeholder")} icon="account-outline" testID="q-name" />
              <Field value={qContact} onChangeText={setQContact} placeholder={t("booking.email_placeholder")} icon="email-outline" autoCapitalize="none" testID="q-contact" />
              <Field value={qMessage} onChangeText={setQMessage} placeholder={t("booking.message_placeholder")} icon="message-text-outline" multiline testID="q-message" />
              <Button testID="q-send" label={t("booking.submit")} icon="send" onPress={sendQuestion} loading={sending} />
            </Animated.View>
          ) : null}
        </Card>

        {/* FAQ */}
        <Text style={s.sectionTitle}>FAQ</Text>
        {faqs.isLoading ? (
          <Loading />
        ) : (faqs.data ?? []).length === 0 ? (
          <EmptyState icon="frequently-asked-questions" title="—" subtitle="Nessuna FAQ disponibile" />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {(faqs.data ?? []).map((f) => {
              const isOpen = open === f.id;
              return (
                <Pressable key={f.id} testID={`faq-${f.id}`} onPress={() => toggle(f.id)}>
                  <Card>
                    <View style={s.faqHead}>
                      <Text style={s.faqQ}>{f.question}</Text>
                      <Icon name={isOpen ? "chevron-up" : "chevron-down"} size={22} color={colors.brandPrimary} />
                    </View>
                    {isOpen ? <Text style={s.faqA}>{f.answer}</Text> : null}
                  </Card>
                </Pressable>
              );
            })}
          </View>
        )}

        {/* Contacts */}
        <Text style={s.sectionTitle}>{t("footer.contacts")}</Text>
        <Card style={{ gap: spacing.sm }}>
          <Pressable style={s.contactRow} onPress={() => Linking.openURL("mailto:info@appartamentomatteo.it")}>
            <Icon name="email-outline" size={20} color={colors.olive} />
            <Text style={s.contactTxt}>info@appartamentomatteo.it</Text>
          </Pressable>
          <View style={s.contactRow}>
            <Icon name="map-marker-outline" size={20} color={colors.olive} />
            <Text style={s.contactTxt}>Trappeto (PA), Sicilia</Text>
          </View>
          <Text style={s.copyright}>{t("footer.copyright", { year: new Date().getFullYear() })}</Text>
        </Card>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  adminBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: c.border },
  ctaTitle: { color: c.onBrandPrimary, fontSize: 12, fontWeight: "700", letterSpacing: 1.5, fontFamily: fonts.body },
  ctaDesc: { color: "rgba(255,255,255,0.9)", fontSize: 14, lineHeight: 20, marginTop: 6, fontFamily: fonts.body },
  sectionTitle: { color: c.onSurface, fontSize: 22, fontFamily: fonts.heading, marginTop: spacing.xl, marginBottom: spacing.md },
  faqHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  faqQ: { color: c.onSurface, fontSize: 15, fontFamily: fonts.body, fontWeight: "600", flex: 1 },
  faqA: { color: c.onSurfaceSecondary, fontSize: 14, lineHeight: 21, marginTop: spacing.sm, fontFamily: fonts.body },
  contactRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  contactTxt: { color: c.onSurface, fontSize: 15, fontFamily: fonts.body },
  copyright: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginTop: spacing.sm },
}));
