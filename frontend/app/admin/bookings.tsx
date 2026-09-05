import React, { useEffect } from "react";
import { View, Text, FlatList, Pressable } from "react-native";
import { router } from "expo-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, EmptyState, Loading, Button, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";
import { euro, prettyDate } from "@/src/lib/format";

type Booking = {
  id: string;
  guest_name: string;
  guest_email: string;
  guest_phone?: string;
  check_in: string;
  check_out: string;
  guests: number;
  status: "pending" | "approved" | "rejected";
  confirmation_code?: string | null;
  quote?: { total: number };
  source?: string;
};

export default function AdminBookings() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const bookings = useQuery({
    queryKey: ["admin-bookings"],
    enabled: !!token,
    queryFn: async () => (await api.get<Booking[]>("/bookings")).data,
  });

  const approve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/bookings/${id}/approve`)).data,
    onSuccess: () => {
      toast.show("Prenotazione approvata", "success");
      qc.invalidateQueries({ queryKey: ["admin-bookings"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
      qc.invalidateQueries({ queryKey: ["availability"] });
    },
    onError: (e: any) => toast.show(e?.response?.data?.detail || "Errore", "error"),
  });

  const reject = useMutation({
    mutationFn: async (id: string) => (await api.post(`/bookings/${id}/reject`)).data,
    onSuccess: () => {
      toast.show("Prenotazione rifiutata", "info");
      qc.invalidateQueries({ queryKey: ["admin-bookings"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
    },
    onError: (e: any) => toast.show(e?.response?.data?.detail || "Errore", "error"),
  });

  if (loading || !token) return <Loading />;

  const statusMeta = (st: Booking["status"]) => {
    if (st === "approved") return { color: colors.success, label: "Approvata", icon: "check-decagram" as const };
    if (st === "rejected") return { color: colors.error, label: "Rifiutata", icon: "close-circle" as const };
    return { color: colors.warning, label: "In attesa", icon: "clock-outline" as const };
  };

  const renderItem = ({ item }: { item: Booking }) => {
    const meta = statusMeta(item.status);
    return (
      <Card style={{ gap: spacing.sm }}>
        <View style={s.head}>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{item.guest_name}</Text>
            <Text style={s.email}>{item.guest_email}</Text>
          </View>
          <View style={[s.statusPill, { backgroundColor: meta.color + "22" }]}>
            <Icon name={meta.icon} size={14} color={meta.color} />
            <Text style={[s.statusTxt, { color: meta.color }]}>{meta.label}</Text>
          </View>
        </View>
        <View style={s.metaRow}>
          <Icon name="calendar-range" size={16} color={colors.olive} />
          <Text style={s.metaTxt}>
            {prettyDate(item.check_in)} → {prettyDate(item.check_out)}
          </Text>
        </View>
        <View style={s.metaRow}>
          <Icon name="account-group" size={16} color={colors.olive} />
          <Text style={s.metaTxt}>{item.guests} ospiti · {euro(item.quote?.total ?? 0)}</Text>
        </View>
        {item.guest_phone ? (
          <View style={s.metaRow}>
            <Icon name="phone" size={16} color={colors.olive} />
            <Text style={s.metaTxt}>{item.guest_phone}</Text>
          </View>
        ) : null}
        {item.confirmation_code ? (
          <View style={s.codeBox}>
            <Icon name="key-variant" size={16} color={colors.brandPrimary} />
            <Text style={s.codeTxt}>{item.confirmation_code}</Text>
          </View>
        ) : null}
        {item.status === "pending" ? (
          <View style={s.actions}>
            <View style={{ flex: 1 }}>
              <Button testID={`approve-${item.id}`} label="Approva" icon="check" small onPress={() => approve.mutate(item.id)} loading={approve.isPending} />
            </View>
            <View style={{ flex: 1 }}>
              <Button testID={`reject-${item.id}`} label="Rifiuta" icon="close" variant="outline" small onPress={() => reject.mutate(item.id)} loading={reject.isPending} />
            </View>
          </View>
        ) : null}
      </Card>
    );
  };

  return (
    <View style={s.screen}>
      <Header title="Prenotazioni" kicker="Admin" showBack showLang={false} />
      {bookings.isLoading ? (
        <Loading />
      ) : (
        <FlatList
          testID="admin-bookings-list"
          data={bookings.data ?? []}
          keyExtractor={(b) => b.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl }}
          ListEmptyComponent={<EmptyState icon="calendar-blank-outline" title="Nessuna prenotazione" subtitle="Le richieste appariranno qui" />}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  head: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  name: { color: c.onSurface, fontSize: 17, fontFamily: fonts.heading },
  email: { color: c.muted, fontSize: 13, fontFamily: fonts.body },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  statusTxt: { fontSize: 12, fontWeight: "700", fontFamily: fonts.body },
  metaRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  metaTxt: { color: c.onSurfaceSecondary, fontSize: 14, fontFamily: fonts.body },
  codeBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.surfaceTertiary, padding: spacing.sm, borderRadius: radius.md, alignSelf: "flex-start" },
  codeTxt: { color: c.brandPrimary, fontSize: 15, fontWeight: "700", fontFamily: fonts.body, letterSpacing: 1 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: 4 },
}));
