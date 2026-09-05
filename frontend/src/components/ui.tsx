import React, { createContext, useCallback, useContext, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  Text,
  View,
  TextInput,
  ScrollView,
} from "react-native";
import Animated, { FadeInDown, FadeOutUp } from "react-native-reanimated";
import * as Haptics from "expo-haptics";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { Icon, IconName } from "./Icon";

/* ----------------------------- Button ----------------------------- */
export function Button({
  label,
  onPress,
  variant = "primary",
  icon,
  loading,
  disabled,
  testID,
  small,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "outline" | "olive";
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  testID?: string;
  small?: boolean;
}) {
  const s = useButtonStyles();
  const { colors } = useTheme();
  const bg =
    variant === "primary"
      ? colors.brandPrimary
      : variant === "olive"
        ? colors.olive
        : variant === "secondary"
          ? colors.brandSecondary
          : "transparent";
  const fg =
    variant === "primary"
      ? colors.onBrandPrimary
      : variant === "olive"
        ? colors.onOlive
        : variant === "secondary"
          ? colors.onBrandSecondary
          : colors.brandPrimary;
  return (
    <Pressable
      testID={testID}
      disabled={disabled || loading}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        onPress();
      }}
      style={({ pressed }) => [
        s.btn,
        small && s.btnSmall,
        { backgroundColor: bg },
        variant === "outline" && { borderWidth: 1.5, borderColor: colors.brandPrimary },
        (disabled || loading) && { opacity: 0.5 },
        pressed && { opacity: 0.85, transform: [{ scale: 0.98 }] },
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon ? <Icon name={icon} size={small ? 16 : 18} color={fg} /> : null}
          <Text style={[s.label, small && { fontSize: 14 }, { color: fg }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

const useButtonStyles = makeStyles((c) => ({
  btn: {
    minHeight: 52,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  btnSmall: { minHeight: 40, paddingHorizontal: spacing.md },
  label: { fontSize: 16, fontWeight: "600", fontFamily: fonts.body },
}));

/* ----------------------------- Card ----------------------------- */
export function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  const s = useCardStyles();
  return <View style={[s.card, style]}>{children}</View>;
}
const useCardStyles = makeStyles((c) => ({
  card: {
    backgroundColor: c.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: c.border,
    shadowColor: "#2C2A28",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
}));

/* ----------------------------- Kicker + Title ----------------------------- */
export function SectionTitle({ kicker, title }: { kicker?: string; title: string }) {
  const s = useTitleStyles();
  return (
    <View style={s.wrap}>
      {kicker ? <Text style={s.kicker}>{kicker.toUpperCase()}</Text> : null}
      <Text style={s.title}>{title}</Text>
    </View>
  );
}
const useTitleStyles = makeStyles((c) => ({
  wrap: { marginBottom: spacing.md },
  kicker: { color: c.brand, fontSize: 11, letterSpacing: 2.5, fontWeight: "700", fontFamily: fonts.body },
  title: { color: c.onSurface, fontSize: 28, fontFamily: fonts.heading, marginTop: 4, lineHeight: 32 },
}));

/* ----------------------------- Input ----------------------------- */
export function Field({
  value,
  onChangeText,
  placeholder,
  icon,
  keyboardType,
  secureTextEntry,
  multiline,
  testID,
  autoCapitalize,
}: {
  value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
  icon?: IconName;
  keyboardType?: any;
  secureTextEntry?: boolean;
  multiline?: boolean;
  testID?: string;
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
}) {
  const s = useFieldStyles();
  const { colors } = useTheme();
  return (
    <View style={[s.wrap, multiline && { alignItems: "flex-start", paddingVertical: 12 }]}>
      {icon ? <Icon name={icon} size={18} color={colors.muted} /> : null}
      <TextInput
        testID={testID}
        style={[s.input, multiline && { minHeight: 90, textAlignVertical: "top" }]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        keyboardType={keyboardType}
        secureTextEntry={secureTextEntry}
        multiline={multiline}
        autoCapitalize={autoCapitalize}
      />
    </View>
  );
}
const useFieldStyles = makeStyles((c) => ({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: c.surfaceTertiary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 52,
    borderWidth: 1,
    borderColor: c.border,
  },
  input: { flex: 1, color: c.onSurface, fontSize: 16, fontFamily: fonts.body, paddingVertical: 8 },
}));

/* ----------------------------- Chips row ----------------------------- */
export function ChipRow({
  items,
  selected,
  onSelect,
}: {
  items: { key: string; label: string; icon?: IconName }[];
  selected: string;
  onSelect: (k: string) => void;
}) {
  const s = useChipStyles();
  const { colors } = useTheme();
  return (
    <View style={s.rowWrap}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={s.rowContent}
      >
        {items.map((it) => {
          const active = it.key === selected;
          return (
            <Pressable
              key={it.key}
              testID={`chip-${it.key}`}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                onSelect(it.key);
              }}
              style={[
                s.chip,
                { backgroundColor: active ? colors.brandPrimary : colors.surfaceTertiary, borderColor: active ? colors.brandPrimary : colors.border },
              ]}
            >
              {it.icon ? (
                <Icon name={it.icon} size={15} color={active ? colors.onBrandPrimary : colors.onSurfaceTertiary} />
              ) : null}
              <Text style={[s.chipTxt, { color: active ? colors.onBrandPrimary : colors.onSurfaceTertiary }]}>
                {it.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}
const useChipStyles = makeStyles((c) => ({
  rowWrap: { height: 56, justifyContent: "center" },
  rowContent: { gap: spacing.sm, paddingHorizontal: spacing.md, alignItems: "center" },
  chip: {
    height: 36,
    flexShrink: 0,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
  },
  chipTxt: { fontSize: 13, fontWeight: "600", fontFamily: fonts.body },
}));

/* ----------------------------- States ----------------------------- */
export function Loading({ label }: { label?: string }) {
  const { colors } = useTheme();
  const s = useStateStyles();
  return (
    <View style={s.center}>
      <ActivityIndicator color={colors.brandPrimary} size="large" />
      {label ? <Text style={s.stateTxt}>{label}</Text> : null}
    </View>
  );
}
export function EmptyState({ icon, title, subtitle }: { icon: IconName; title: string; subtitle?: string }) {
  const { colors } = useTheme();
  const s = useStateStyles();
  return (
    <View style={s.center}>
      <Icon name={icon} size={44} color={colors.borderStrong} />
      <Text style={s.stateTitle}>{title}</Text>
      {subtitle ? <Text style={s.stateTxt}>{subtitle}</Text> : null}
    </View>
  );
}
const useStateStyles = makeStyles((c) => ({
  center: { alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  stateTitle: { color: c.onSurface, fontSize: 18, fontFamily: fonts.heading, marginTop: 4 },
  stateTxt: { color: c.muted, fontSize: 14, textAlign: "center", fontFamily: fonts.body },
}));

/* ----------------------------- Toast ----------------------------- */
type Toast = { id: number; msg: string; kind: "success" | "error" | "info" };
const ToastCtx = createContext<{ show: (msg: string, kind?: Toast["kind"]) => void }>({
  show: () => {},
});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const s = useToastStyles();
  const { colors } = useTheme();
  const show = useCallback((msg: string, kind: Toast["kind"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    Haptics.notificationAsync(
      kind === "error" ? Haptics.NotificationFeedbackType.Error : Haptics.NotificationFeedbackType.Success,
    ).catch(() => {});
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <View style={s.host} pointerEvents="box-none">
        {toasts.map((t) => {
          const bg = t.kind === "error" ? colors.error : t.kind === "success" ? colors.success : colors.surfaceInverse;
          const fg = t.kind === "info" ? colors.onSurfaceInverse : colors.onError;
          return (
            <Animated.View key={t.id} entering={FadeInDown} exiting={FadeOutUp} style={[s.toast, { backgroundColor: bg }]}>
              <Icon
                name={t.kind === "error" ? "alert-circle" : t.kind === "success" ? "check-circle" : "information"}
                size={18}
                color={fg}
              />
              <Text style={[s.toastTxt, { color: fg }]}>{t.msg}</Text>
            </Animated.View>
          );
        })}
      </View>
    </ToastCtx.Provider>
  );
}
const useToastStyles = makeStyles((c) => ({
  host: { position: "absolute", top: 60, left: 0, right: 0, alignItems: "center", gap: spacing.sm, zIndex: 9999 },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    borderRadius: radius.md,
    maxWidth: "90%",
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  toastTxt: { fontSize: 14, fontWeight: "600", fontFamily: fonts.body, flexShrink: 1 },
}));
