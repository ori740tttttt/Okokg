import React, { useEffect } from "react";
import { View, Text, ScrollView, RefreshControl } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Loading, SectionTitle } from "@/src/components/ui";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

export default function AdminStats() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const qc = useQueryClient();

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const stats = useQuery({
    queryKey: ["admin-stats"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/stats")).data,
  });

  if (loading || !token) return <Loading />;
  const st = stats.data;

  const kpis: { icon: IconName; label: string; value: string | number; tint: string }[] = [
    { icon: "email-fast-outline", label: "In attesa", value: st?.pending_bookings ?? 0, tint: colors.warning },
    { icon: "check-decagram", label: "Approvate", value: st?.approved_bookings ?? 0, tint: colors.success },
    { icon: "close-circle-outline", label: "Rifiutate", value: st?.rejected_bookings ?? 0, tint: colors.error },
    { icon: "calendar-multiple-check", label: "Totali", value: st?.total_bookings ?? 0, tint: colors.brandPrimary },
    { icon: "eye-outline", label: "Visite", value: st?.total_visits ?? 0, tint: colors.info },
    { icon: "trending-up", label: "Conversione", value: `${st?.conversion_rate ?? 0}%`, tint: colors.olive },
  ];

  const daily: { day: string; count: number }[] = st?.daily_visits ?? [];
  const maxDay = Math.max(1, ...daily.map((d) => d.count));

  return (
    <View style={s.screen}>
      <Header title="Statistiche" kicker="Admin" showBack showLang={false} />
      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["admin-stats"] })} tintColor={colors.brandPrimary} />}
      >
        {stats.isLoading ? (
          <Loading />
        ) : (
          <>
            <View style={s.grid}>
              {kpis.map((k) => (
                <Card key={k.label} style={s.kpi} testID={`stat-${k.label}`}>
                  <View style={[s.kpiIcon, { backgroundColor: k.tint + "22" }]}>
                    <Icon name={k.icon} size={20} color={k.tint} />
                  </View>
                  <Text style={s.kpiVal}>{k.value}</Text>
                  <Text style={s.kpiLabel}>{k.label}</Text>
                </Card>
              ))}
            </View>

            <SectionTitle title="Provenienza prenotazioni" />
            <Card style={{ marginBottom: spacing.lg }}>
              <View style={s.srcRow}>
                <View style={s.srcItem}>
                  <Icon name="web" size={22} color={colors.brandPrimary} />
                  <Text style={s.srcVal}>{st?.site_bookings ?? 0}</Text>
                  <Text style={s.srcLabel}>Sito</Text>
                </View>
                <View style={s.srcDivider} />
                <View style={s.srcItem}>
                  <Icon name="alpha-b-box" size={22} color={colors.info} />
                  <Text style={s.srcVal}>{st?.booking_com_bookings ?? 0}</Text>
                  <Text style={s.srcLabel}>Booking.com</Text>
                </View>
              </View>
            </Card>

            <SectionTitle title="Visite (ultimi 30 giorni)" />
            <Card>
              {daily.length === 0 ? (
                <Text style={s.emptyTxt}>Ancora nessuna visita registrata.</Text>
              ) : (
                <View style={s.chart}>
                  {daily.map((d) => (
                    <View key={d.day} style={s.barCol}>
                      <View style={[s.bar, { height: 8 + (d.count / maxDay) * 90, backgroundColor: colors.brandPrimary }]} />
                    </View>
                  ))}
                </View>
              )}
              {daily.length > 0 ? (
                <Text style={s.chartHint}>{daily[0].day} → {daily[daily.length - 1].day}</Text>
              ) : null}
            </Card>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  kpi: { flexGrow: 1, minWidth: "30%", alignItems: "flex-start", gap: 4, padding: spacing.sm },
  kpiIcon: { width: 36, height: 36, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  kpiVal: { color: c.onSurface, fontSize: 22, fontFamily: fonts.heading, marginTop: 2 },
  kpiLabel: { color: c.muted, fontSize: 11, fontFamily: fonts.body },
  srcRow: { flexDirection: "row", alignItems: "center" },
  srcItem: { flex: 1, alignItems: "center", gap: 4 },
  srcDivider: { width: 1, height: 48, backgroundColor: c.divider },
  srcVal: { color: c.onSurface, fontSize: 24, fontFamily: fonts.heading },
  srcLabel: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  chart: { flexDirection: "row", alignItems: "flex-end", gap: 3, height: 100 },
  barCol: { flex: 1, justifyContent: "flex-end", alignItems: "center" },
  bar: { width: "70%", borderRadius: 3, minHeight: 4 },
  chartHint: { color: c.muted, fontSize: 11, fontFamily: fonts.body, marginTop: spacing.sm, textAlign: "center" },
  emptyTxt: { color: c.muted, fontSize: 14, fontFamily: fonts.body, textAlign: "center", paddingVertical: spacing.md },
}));
