import React, { useState } from "react";
import { Modal, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { router } from "expo-router";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import i18n, { SUPPORTED_LANGUAGES } from "@/src/i18n";
import { Icon } from "./Icon";

export function Header({
  title,
  kicker,
  showBack,
  showLang = true,
  right,
}: {
  title: string;
  kicker?: string;
  showBack?: boolean;
  showLang?: boolean;
  right?: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  const s = useStyles();
  const { colors } = useTheme();
  const [langOpen, setLangOpen] = useState(false);

  return (
    <View style={[s.wrap, { paddingTop: insets.top + spacing.sm }]}>
      <View style={s.row}>
        <View style={s.left}>
          {showBack ? (
            <Pressable testID="header-back" onPress={() => router.back()} style={s.iconBtn} hitSlop={10}>
              <Icon name="chevron-left" size={26} color={colors.onSurface} />
            </Pressable>
          ) : null}
          <View style={{ flexShrink: 1 }}>
            {kicker ? <Text style={s.kicker}>{kicker.toUpperCase()}</Text> : null}
            <Text style={s.title} numberOfLines={1}>
              {title}
            </Text>
          </View>
        </View>
        <View style={s.rightRow}>
          {right}
          {showLang ? (
            <Pressable testID="header-lang" onPress={() => setLangOpen(true)} style={s.langBtn} hitSlop={8}>
              <Text style={s.flag}>
                {SUPPORTED_LANGUAGES.find((l) => l.code === i18n.language)?.flag ?? "🌐"}
              </Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      <Modal visible={langOpen} transparent animationType="fade" onRequestClose={() => setLangOpen(false)}>
        <Pressable style={s.backdrop} onPress={() => setLangOpen(false)}>
          <View style={s.sheet}>
            <Text style={s.sheetTitle}>Lingua · Language</Text>
            {SUPPORTED_LANGUAGES.map((l) => {
              const active = l.code === i18n.language;
              return (
                <Pressable
                  key={l.code}
                  testID={`lang-${l.code}`}
                  style={[s.langRow, active && { backgroundColor: colors.surfaceTertiary }]}
                  onPress={() => {
                    i18n.changeLanguage(l.code);
                    setLangOpen(false);
                  }}
                >
                  <Text style={s.flag}>{l.flag}</Text>
                  <Text style={s.langLabel}>{l.label}</Text>
                  {active ? <Icon name="check" size={20} color={colors.brandPrimary} /> : null}
                </Pressable>
              );
            })}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: {
    backgroundColor: c.surface,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: c.divider,
  },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 44 },
  left: { flexDirection: "row", alignItems: "center", gap: spacing.xs, flexShrink: 1 },
  iconBtn: { padding: 4, marginLeft: -4 },
  kicker: { color: c.brand, fontSize: 10, letterSpacing: 2, fontWeight: "700", fontFamily: fonts.body },
  title: { color: c.onSurface, fontSize: 24, fontFamily: fonts.heading },
  rightRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  langBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: c.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: c.border,
  },
  flag: { fontSize: 20 },
  backdrop: { flex: 1, backgroundColor: "rgba(44,42,40,0.45)", justifyContent: "center", padding: spacing.lg },
  sheet: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, gap: 4 },
  sheetTitle: { color: c.onSurface, fontSize: 18, fontFamily: fonts.heading, marginBottom: spacing.sm },
  langRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: 14,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
  },
  langLabel: { flex: 1, color: c.onSurface, fontSize: 16, fontFamily: fonts.body, fontWeight: "500" },
}));
