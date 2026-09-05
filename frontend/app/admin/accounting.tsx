import React, { useEffect } from "react";
import { View, Text, ScrollView, RefreshControl } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Loading, SectionTitle, EmptyState } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";
import { euro } from "@/src/lib/format";

export default function AdminAccounting() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const qc = useQueryClient();

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const acc = useQuery({
    queryKey: ["admin-accounting"],
    enabled: !!token,
    queryFn: async () => (await api.get("/admin/accounting")).data,
  });

  if (loading || !token) return <Loading />;
  const t = acc.data?.totals;
  const rates = acc.data?.rates;
  const items: any[] = acc.data?.items ?? [];

  return (
    <View style={s.screen}>
      <Header title="Contabilità" kicker="Admin" showBack showLang={false} />
      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["admin-accounting"] })} tintColor={colors.brandPrimary} />}
      >
        {acc.isLoading ? (
          <Loading />
        ) : (
          <>
            <View style={s.bigRow}>
              <Card style={[s.bigCard, { backgroundColor: colors.brandPrimary }]} testID="acc-gross">
                <Text style={[s.bigLabel, { color: colors.onBrandPrimary }]}>LORDO TOTALE</Text>
                <Text style={[s.bigVal, { color: colors.onBrandPrimary }]}>{euro(t?.gross_total ?? 0)}</Text>
              </Card>
              <Card style={[s.bigCard, { backgroundColor: colors.olive }]} testID="acc-net">
                <Text style={[s.bigLabel, { color: colors.onOlive }]}>NETTO TOTALE</Text>
                <Text style={[s.bigVal, { color: colors.onOlive }]}>{euro(t?.net_total ?? 0)}</Text>
              </Card>
            </View>

            <View style={s.twoRow}>
              <Card style={s.halfCard}>
                <View style={s.srcHead}>
                  <Icon name="web" size={18} color={colors.brandPrimary} />
                  <Text style={s.srcTitle}>Sito</Text>
                </View>
                <Text style={s.rowLine}>Lordo <Text style={s.rowStrong}>{euro(t?.site_gross ?? 0)}</Text></Text>
                <Text style={s.rowLine}>Netto <Text style={s.rowStrong}>{euro(t?.site_net ?? 0)}</Text></Text>
              </Card>
              <Card style={s.halfCard}>
                <View style={s.srcHead}>
                  <Icon name="alpha-b-box" size={18} color={colors.info} />
                  <Text style={s.srcTitle}>Booking.com</Text>
                </View>
                <Text style={s.rowLine}>Lordo <Text style={s.rowStrong}>{euro(t?.booking_gross ?? 0)}</Text></Text>
                <Text style={s.rowLine}>Netto <Text style={s.rowStrong}>{euro(t?.booking_net ?? 0)}</Text></Text>
              </Card>
            </View>

            <SectionTitle title="Trattenute Booking.com" />
            <Card style={{ marginBottom: spacing.lg }}>
              <CommRow label={`Tassa di Stato (${rates?.state_pct ?? 21}%)`} value={t?.by_commission?.state} c={colors} />
              <CommRow label={`Commissione Booking (${rates?.booking_pct ?? 15}%)`} value={t?.by_commission?.booking} c={colors} />
              <CommRow label={`IVA (${rates?.vat_pct ?? 3.7}%)`} value={t?.by_commission?.vat} c={colors} />
              <CommRow label={`Banca (${rates?.bank_pct ?? 1.5}%)`} value={t?.by_commission?.bank} c={colors} last />
              <View style={s.totComm}>
                <Text style={s.totCommLabel}>Totale trattenute</Text>
                <Text style={s.totCommVal}>- {euro(t?.commissions_total ?? 0)}</Text>
              </View>
            </Card>

            <SectionTitle title={`Prenotazioni approvate (${items.length})`} />
            {items.length === 0 ? (
              <EmptyState icon="cash-remove" title="Nessun movimento" subtitle="Le prenotazioni approvate compaiono qui." />
            ) : (
              <View style={{ gap: spacing.sm }}>
                {items.map((it) => (
                  <Card key={it.id} style={s.item} testID={`acc-item-${it.id}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.itemName}>{it.guest_name}</Text>
                      <Text style={s.itemMeta}>{it.check_in} → {it.check_out}</Text>
                      <View style={[s.badge, { backgroundColor: it.source === "booking" ? colors.info + "22" : colors.brandPrimary + "22" }]}>
                        <Text style={[s.badgeTxt, { color: it.source === "booking" ? colors.info : colors.brandPrimary }]}>
                          {it.source === "booking" ? "Booking.com" : "Sito"}
                        </Text>
                      </View>
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={s.itemGross}>{euro(it.breakdown?.gross ?? 0)}</Text>
                      <Text style={s.itemNet}>netto {euro(it.breakdown?.net ?? 0)}</Text>
                    </View>
                  </Card>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function CommRow({ label, value, c, last }: { label: string; value?: number; c: any; last?: boolean }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: last ? 0 : 1, borderBottomColor: c.divider }}>
      <Text style={{ color: c.muted, fontSize: 14, fontFamily: fonts.body }}>{label}</Text>
      <Text style={{ color: c.onSurface, fontSize: 14, fontFamily: fonts.body, fontWeight: "600" }}>- {euro(value ?? 0)}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  bigRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  bigCard: { flex: 1, borderWidth: 0 },
  bigLabel: { fontSize: 11, letterSpacing: 1.5, fontFamily: fonts.body, fontWeight: "700", opacity: 0.9 },
  bigVal: { fontSize: 24, fontFamily: fonts.heading, marginTop: 6 },
  twoRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg },
  halfCard: { flex: 1, gap: 4 },
  srcHead: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 },
  srcTitle: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  rowLine: { color: c.muted, fontSize: 13, fontFamily: fonts.body },
  rowStrong: { color: c.onSurface, fontWeight: "700" },
  totComm: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: c.borderStrong },
  totCommLabel: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  totCommVal: { color: c.error, fontSize: 16, fontFamily: fonts.heading },
  item: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  itemName: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  itemMeta: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginTop: 2 },
  badge: { alignSelf: "flex-start", borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2, marginTop: 6 },
  badgeTxt: { fontSize: 11, fontFamily: fonts.body, fontWeight: "700" },
  itemGross: { color: c.onSurface, fontSize: 16, fontFamily: fonts.heading },
  itemNet: { color: c.olive, fontSize: 12, fontFamily: fonts.body, marginTop: 2 },
}));
