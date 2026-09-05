import React, { useMemo, useState } from "react";
import { View, Text, Pressable, Switch } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, router } from "expo-router";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Button, Card, Field, SectionTitle, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { api } from "@/src/lib/api";
import { euro, prettyDate, nightsBetween } from "@/src/lib/format";

export default function BookingScreen() {
  const params = useLocalSearchParams<{ start?: string; end?: string }>();
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();

  const [guests, setGuests] = useState(2);
  const [ac, setAc] = useState(false);
  const [discount, setDiscount] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const start = params.start || "";
  const end = params.end || "";
  const nights = nightsBetween(start, end);
  const canQuote = !!start && !!end && nights > 0;

  const quoteBody = useMemo(
    () => ({
      guest_name: name || "x",
      guest_email: email || "x@x.it",
      check_in: start,
      check_out: end,
      guests,
      extras: { ac },
      discount_code: discount || null,
    }),
    [name, email, start, end, guests, ac, discount],
  );

  const quote = useQuery({
    queryKey: ["quote", start, end, guests, ac, discount],
    enabled: canQuote,
    queryFn: async () => (await api.post("/quote", quoteBody)).data,
  });

  const submit = async () => {
    if (!canQuote) return toast.show(t("booking.toast_select_dates"), "error");
    if (!name.trim() || !email.trim()) return toast.show(t("booking.toast_need_name_email"), "error");
    if (!phone.trim()) return toast.show(t("booking.toast_need_phone"), "error");
    setSubmitting(true);
    try {
      await api.post("/bookings", {
        guest_name: name,
        guest_email: email,
        guest_phone: phone,
        check_in: start,
        check_out: end,
        guests,
        extras: { ac },
        discount_code: discount || null,
        message: message || null,
      });
      toast.show(t("booking.toast_sent"), "success");
      router.back();
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || t("booking.toast_error"), "error");
    } finally {
      setSubmitting(false);
    }
  };

  const q = quote.data;

  return (
    <View style={s.screen}>
      <Header title={t("booking.title")} showBack showLang={false} />
      <KeyboardAwareScrollView
        testID="booking-scroll"
        contentContainerStyle={{ padding: spacing.md, paddingBottom: insets.bottom + spacing.xxl }}
        bottomOffset={20}
        showsVerticalScrollIndicator={false}
      >
        {/* Dates summary */}
        <Card>
          <View style={s.datesRow}>
            <View style={s.dateBox}>
              <Text style={s.dateLabel}>{t("booking.checkin")}</Text>
              <Text style={s.dateVal}>{prettyDate(start)}</Text>
            </View>
            <Icon name="arrow-right" size={20} color={colors.muted} />
            <View style={s.dateBox}>
              <Text style={s.dateLabel}>{t("booking.checkout")}</Text>
              <Text style={s.dateVal}>{prettyDate(end)}</Text>
            </View>
          </View>
          <Pressable testID="booking-change-dates" onPress={() => router.back()} style={s.changeDates}>
            <Icon name="calendar-edit" size={16} color={colors.brandPrimary} />
            <Text style={s.changeDatesTxt}>{nights > 0 ? `${nights} notti` : t("booking.toast_select_dates")}</Text>
          </Pressable>
        </Card>

        {/* Guests + AC */}
        <Card style={{ marginTop: spacing.md, gap: spacing.md }}>
          <View style={s.stepperRow}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Icon name="account-group-outline" size={20} color={colors.olive} />
              <Text style={s.rowLabel}>{t("booking.guests")}</Text>
            </View>
            <View style={s.stepper}>
              <Pressable testID="guests-minus" onPress={() => setGuests((g) => Math.max(1, g - 1))} style={s.stepBtn}>
                <Icon name="minus" size={18} color={colors.onSurface} />
              </Pressable>
              <Text style={s.stepVal}>{guests}</Text>
              <Pressable testID="guests-plus" onPress={() => setGuests((g) => Math.min(10, g + 1))} style={s.stepBtn}>
                <Icon name="plus" size={18} color={colors.onSurface} />
              </Pressable>
            </View>
          </View>
          <View style={s.divider} />
          <View style={s.stepperRow}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Icon name="snowflake" size={20} color={colors.info} />
              <Text style={s.rowLabel}>{t("booking.ac")}</Text>
            </View>
            <Switch
              testID="ac-switch"
              value={ac}
              onValueChange={setAc}
              trackColor={{ true: colors.olive, false: colors.border }}
              thumbColor="#fff"
            />
          </View>
        </Card>

        {/* Discount */}
        <View style={{ marginTop: spacing.md }}>
          <Field value={discount} onChangeText={setDiscount} placeholder={t("booking.discount_code")} icon="ticket-percent-outline" autoCapitalize="characters" testID="discount-code" />
        </View>

        {/* Quote breakdown */}
        {canQuote && q ? (
          <Card style={{ marginTop: spacing.md, gap: spacing.sm }}>
            <SectionTitle title={t("booking.site_total")} />
            <QuoteRow label={t("booking.n_nights", { n: q.nights })} value={euro(q.nightly_total)} />
            {q.extra_guest_fees > 0 ? <QuoteRow label={t("booking.extra_guests")} value={euro(q.extra_guest_fees)} /> : null}
            {q.ac_fee > 0 ? <QuoteRow label={t("booking.ac")} value={euro(q.ac_fee)} /> : null}
            <QuoteRow label={t("booking.cleaning")} value={euro(q.cleaning_fee)} />
            <QuoteRow label={t("booking.tourist_tax")} value={euro(q.tourist_tax)} />
            {q.discount_amount > 0 ? (
              <QuoteRow
                label={t("booking.discount_label", { code: q.discount_info?.code, percent: q.discount_info?.percent })}
                value={`- ${euro(q.discount_amount)}`}
                highlight
              />
            ) : null}
            <View style={s.divider} />
            <View style={s.totalRow}>
              <Text style={s.totalLabel}>{t("booking.site_total")}</Text>
              <Text style={s.totalVal}>{euro(q.total)}</Text>
            </View>
            {q.savings > 0 ? (
              <View style={s.savings}>
                <Icon name="tag-heart" size={15} color={colors.success} />
                <Text style={s.savingsTxt}>{t("booking.save_here", { amount: euro(q.savings) })}</Text>
              </View>
            ) : null}
          </Card>
        ) : null}

        {/* Guest details */}
        <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
          <Field value={name} onChangeText={setName} placeholder={t("booking.name_placeholder")} icon="account-outline" testID="guest-name" autoCapitalize="words" />
          <Field value={email} onChangeText={setEmail} placeholder={t("booking.email_placeholder")} icon="email-outline" keyboardType="email-address" autoCapitalize="none" testID="guest-email" />
          <Field value={phone} onChangeText={setPhone} placeholder={t("booking.phone_placeholder")} icon="phone-outline" keyboardType="phone-pad" testID="guest-phone" />
          <Field value={message} onChangeText={setMessage} placeholder={t("booking.message_placeholder")} icon="message-text-outline" multiline testID="guest-message" />
        </View>

        <View style={{ marginTop: spacing.lg }}>
          <Button testID="booking-submit" label={t("booking.submit")} icon="send" onPress={submit} loading={submitting} />
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}

function QuoteRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View style={s.quoteRow}>
      <Text style={[s.quoteLabel, highlight && { color: colors.success }]} numberOfLines={1}>
        {label}
      </Text>
      <Text style={[s.quoteVal, highlight && { color: colors.success }]}>{value}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  datesRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  dateBox: { flex: 1 },
  dateLabel: { color: c.muted, fontSize: 11, letterSpacing: 1, fontFamily: fonts.body, textTransform: "uppercase" },
  dateVal: { color: c.onSurface, fontSize: 17, fontFamily: fonts.heading, marginTop: 2 },
  changeDates: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md, alignSelf: "flex-start" },
  changeDatesTxt: { color: c.brandPrimary, fontSize: 13, fontWeight: "600", fontFamily: fonts.body },
  stepperRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rowLabel: { color: c.onSurface, fontSize: 15, fontFamily: fonts.body, fontWeight: "500" },
  stepper: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: c.surfaceTertiary, borderRadius: radius.pill, paddingHorizontal: 6, paddingVertical: 4 },
  stepBtn: { width: 34, height: 34, borderRadius: radius.pill, backgroundColor: c.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  stepVal: { color: c.onSurface, fontSize: 17, fontFamily: fonts.heading, minWidth: 20, textAlign: "center" },
  divider: { height: 1, backgroundColor: c.divider },
  quoteRow: { flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  quoteLabel: { color: c.onSurfaceSecondary, fontSize: 14, fontFamily: fonts.body, flexShrink: 1 },
  quoteVal: { color: c.onSurface, fontSize: 14, fontFamily: fonts.body, fontWeight: "500" },
  totalRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  totalLabel: { color: c.onSurface, fontSize: 18, fontFamily: fonts.heading },
  totalVal: { color: c.brandPrimary, fontSize: 24, fontFamily: fonts.heading },
  savings: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.surfaceTertiary, padding: spacing.sm, borderRadius: radius.md },
  savingsTxt: { color: c.success, fontSize: 13, fontWeight: "600", fontFamily: fonts.body },
}));
