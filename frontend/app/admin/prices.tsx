import React, { useEffect, useMemo, useState } from "react";
import { View, Text } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { Calendar } from "react-native-calendars";
import { router } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, SectionTitle, Loading, useToast } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";
import { useAvailability } from "@/src/lib/queries";
import { euro } from "@/src/lib/format";

export default function AdminPrices() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const availability = useAvailability();

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [price, setPrice] = useState("");
  const [bookingPrice, setBookingPrice] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const av = availability.data;

  const marked = useMemo(() => {
    const marks: Record<string, any> = {};
    Object.entries(av?.prices ?? {}).forEach(([d, p]) => {
      marks[d] = { marked: true, dotColor: colors.olive };
    });
    Object.keys(selected).forEach((d) => {
      marks[d] = { ...(marks[d] || {}), selected: true, selectedColor: colors.brandPrimary };
    });
    return marks;
  }, [av, selected, colors]);

  const toggleDay = (d: string) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[d]) delete next[d];
      else next[d] = true;
      return next;
    });
  };

  const save = async () => {
    const dates = Object.keys(selected);
    if (dates.length === 0) return toast.show("Seleziona almeno una data", "error");
    if (!price && !bookingPrice) return toast.show("Inserisci un prezzo", "error");
    setSaving(true);
    try {
      await api.post("/prices/bulk", {
        dates,
        price: price ? parseFloat(price) : null,
        booking_price: bookingPrice ? parseFloat(bookingPrice) : null,
      });
      toast.show("Prezzi aggiornati", "success");
      setSelected({});
      setPrice("");
      setBookingPrice("");
      qc.invalidateQueries({ queryKey: ["availability"] });
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !token) return <Loading />;

  const count = Object.keys(selected).length;

  return (
    <View style={s.screen}>
      <Header title="Prezzi & Calendario" kicker="Admin" showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        <Card style={{ marginBottom: spacing.md }}>
          <View style={s.baseRow}>
            <View>
              <Text style={s.baseLabel}>Prezzo base sito</Text>
              <Text style={s.baseVal}>{euro(av?.base_price ?? 0)}</Text>
            </View>
            <View>
              <Text style={s.baseLabel}>Prezzo base Booking</Text>
              <Text style={s.baseVal}>{euro(av?.base_booking_price ?? 0)}</Text>
            </View>
          </View>
        </Card>

        <Card style={{ padding: spacing.sm }}>
          <Calendar
            testID="admin-price-calendar"
            markedDates={marked}
            onDayPress={(d: { dateString: string }) => toggleDay(d.dateString)}
            theme={{
              calendarBackground: colors.surfaceSecondary,
              monthTextColor: colors.onSurface,
              textMonthFontFamily: fonts.heading,
              dayTextColor: colors.onSurface,
              arrowColor: colors.brandPrimary,
              todayTextColor: colors.brandPrimary,
              textDayFontFamily: fonts.body,
            }}
          />
        </Card>

        <View style={{ marginTop: spacing.md }}>
          <SectionTitle title={count > 0 ? `${count} date selezionate` : "Seleziona le date"} />
          <View style={{ gap: spacing.sm }}>
            <Field value={price} onChangeText={setPrice} placeholder="Prezzo sito / notte (€)" icon="cash" keyboardType="numeric" testID="price-site" />
            <Field value={bookingPrice} onChangeText={setBookingPrice} placeholder="Prezzo Booking.com / notte (€)" icon="cash-multiple" keyboardType="numeric" testID="price-booking" />
            <Button testID="save-prices" label="Salva prezzi" icon="content-save" onPress={save} loading={saving} />
          </View>
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  baseRow: { flexDirection: "row", justifyContent: "space-between" },
  baseLabel: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  baseVal: { color: c.onSurface, fontSize: 22, fontFamily: fonts.heading, marginTop: 2 },
}));
