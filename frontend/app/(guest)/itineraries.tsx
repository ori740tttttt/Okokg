import React, { useRef, useState } from "react";
import { View, Text, Pressable, ScrollView, ActivityIndicator, Platform, TextInput } from "react-native";
import { KeyboardAvoidingView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";
import Animated, { FadeInUp } from "react-native-reanimated";

import { Header } from "@/src/components/Header";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { streamCarmelo } from "@/src/lib/api";
import i18n from "@/src/i18n";

type Msg = { id: string; role: "user" | "assistant"; content: string };

const SESSION_ID = `mobile_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

export default function ItinerariesScreen() {
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const suggestions: { label: string; icon: IconName; prompt: string }[] = [
    { label: t("ai_itinerary.style_relax"), icon: "umbrella-beach", prompt: "Consigliami un itinerario di 3 giorni rilassante tra mare e spiagge vicino Trappeto." },
    { label: t("ai_itinerary.style_food"), icon: "silverware-fork-knife", prompt: "Dove posso mangiare piatti tipici siciliani vicino Trappeto? Consigliami un tour gastronomico." },
    { label: t("ai_itinerary.style_culture"), icon: "bank", prompt: "Crea un itinerario culturale di 2 giorni tra Palermo e Trapani con arte e storia." },
    { label: t("ai_itinerary.style_adventure"), icon: "hiking", prompt: "Suggerisci escursioni nella natura e panorami da non perdere in Sicilia occidentale." },
  ];

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    const userMsg: Msg = { id: `u${Date.now()}`, role: "user", content: trimmed };
    const aiId = `a${Date.now()}`;
    setMessages((m) => [...m, userMsg, { id: aiId, role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    try {
      await streamCarmelo(
        "/carmelo/chat",
        { session_id: SESSION_ID, message: `${trimmed}\n\n(Rispondi in lingua: ${i18n.language})`, model: "claude" },
        (_chunk, full) => {
          setMessages((m) => m.map((msg) => (msg.id === aiId ? { ...msg, content: full } : msg)));
        },
      );
    } catch {
      setMessages((m) =>
        m.map((msg) => (msg.id === aiId ? { ...msg, content: t("ai_itinerary.default_error") } : msg)),
      );
    } finally {
      setBusy(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  const empty = messages.length === 0;

  return (
    <View style={s.screen}>
      <Header title="Carmelo IA" kicker={t("ai_itinerary.badge")} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "translate-with-padding" : "height"}
      >
        <ScrollView
          ref={scrollRef}
          testID="carmelo-scroll"
          contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.lg, gap: spacing.md, flexGrow: 1 }}
          showsVerticalScrollIndicator={false}
        >
          {empty ? (
            <View style={s.intro}>
              <View style={s.avatar}>
                <Icon name="robot-happy" size={34} color={colors.onBrandPrimary} />
              </View>
              <Text style={s.introTitle}>{t("ai_itinerary.title")}</Text>
              <Text style={s.introDesc}>{t("ai_itinerary.description")}</Text>
              <View style={s.suggestions}>
                {suggestions.map((sg) => (
                  <Pressable key={sg.label} testID={`suggest-${sg.label}`} style={s.suggestChip} onPress={() => send(sg.prompt)}>
                    <Icon name={sg.icon} size={16} color={colors.brandPrimary} />
                    <Text style={s.suggestTxt}>{sg.label}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : (
            messages.map((m) => (
              <Animated.View
                key={m.id}
                entering={FadeInUp.duration(200)}
                style={[s.bubbleRow, m.role === "user" ? s.rowRight : s.rowLeft]}
              >
                {m.role === "assistant" ? (
                  <View style={s.miniAvatar}>
                    <Icon name="robot-happy" size={16} color={colors.onBrandPrimary} />
                  </View>
                ) : null}
                <View style={[s.bubble, m.role === "user" ? s.userBubble : s.aiBubble]}>
                  {m.content === "" && busy ? (
                    <ActivityIndicator color={colors.brandPrimary} size="small" />
                  ) : (
                    <Text style={[s.bubbleTxt, { color: m.role === "user" ? colors.onBrandPrimary : colors.onSurface }]}>
                      {m.content}
                    </Text>
                  )}
                </View>
              </Animated.View>
            ))
          )}
        </ScrollView>

        <KeyboardStickyView offset={{ closed: 0, opened: insets.bottom }}>
          <View style={[s.inputBar, { paddingBottom: spacing.sm }]}>
            <TextInput
              testID="carmelo-input"
              style={s.input}
              value={input}
              onChangeText={setInput}
              placeholder={t("ai_itinerary.interests_placeholder")}
              placeholderTextColor={colors.muted}
              multiline
              onSubmitEditing={() => send(input)}
            />
            <Pressable
              testID="carmelo-send"
              style={[s.sendBtn, (!input.trim() || busy) && { opacity: 0.4 }]}
              disabled={!input.trim() || busy}
              onPress={() => send(input)}
            >
              <Icon name="send" size={20} color={colors.onBrandPrimary} />
            </Pressable>
          </View>
        </KeyboardStickyView>
      </KeyboardAvoidingView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  intro: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: spacing.xl, gap: spacing.sm },
  avatar: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  introTitle: { color: c.onSurface, fontSize: 24, fontFamily: fonts.heading, textAlign: "center", marginTop: spacing.sm, lineHeight: 28 },
  introDesc: { color: c.muted, fontSize: 14, textAlign: "center", fontFamily: fonts.body, lineHeight: 21 },
  suggestions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, justifyContent: "center", marginTop: spacing.md },
  suggestChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: c.surfaceSecondary,
    borderWidth: 1,
    borderColor: c.border,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
  },
  suggestTxt: { color: c.onSurface, fontSize: 13, fontWeight: "600", fontFamily: fonts.body },
  bubbleRow: { flexDirection: "row", alignItems: "flex-end", gap: 6, maxWidth: "100%" },
  rowLeft: { justifyContent: "flex-start" },
  rowRight: { justifyContent: "flex-end" },
  miniAvatar: { width: 28, height: 28, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  bubble: { maxWidth: "82%", padding: spacing.md, borderRadius: radius.lg },
  userBubble: { backgroundColor: c.brandPrimary, borderBottomRightRadius: 4 },
  aiBubble: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderBottomLeftRadius: 4 },
  bubbleTxt: { fontSize: 15, lineHeight: 22, fontFamily: fonts.body },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    backgroundColor: c.surfaceSecondary,
    borderTopWidth: 1,
    borderTopColor: c.divider,
  },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 44,
    backgroundColor: c.surfaceTertiary,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingTop: 12,
    paddingBottom: 12,
    color: c.onSurface,
    fontSize: 15,
    fontFamily: fonts.body,
  },
  sendBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
}));
