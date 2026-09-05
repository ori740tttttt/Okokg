import React, { useEffect } from "react";
import { View, Text, ScrollView, Pressable, RefreshControl } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Loading } from "@/src/components/ui";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";

export default function AdminDashboard() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading, logout } = useAuth();
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
    { icon: "eye-outline", label: "Visite", value: st?.total_visits ?? 0, tint: colors.info },
    { icon: "trending-up", label: "Conversione", value: `${st?.conversion_rate ?? 0}%`, tint: colors.brandPrimary },
  ];

  const sections: { title: string; tiles: { icon: IconName; label: string; desc: string; route: string }[] }[] = [
    {
      title: "Prenotazioni & resoconti",
      tiles: [
        { icon: "calendar-multiple-check", label: "Prenotazioni", desc: "Approva o rifiuta richieste", route: "/admin/bookings" },
        { icon: "plus-box-outline", label: "Prenotazione manuale", desc: "Inserisci una prenotazione a mano", route: "/admin/manual-booking" },
        { icon: "chart-box-outline", label: "Statistiche", desc: "Visite, conversioni, sorgenti", route: "/admin/stats" },
        { icon: "calculator-variant-outline", label: "Contabilità", desc: "Lordo, netto e trattenute", route: "/admin/accounting" },
      ],
    },
    {
      title: "Il tuo alloggio",
      tiles: [
        { icon: "cash-multiple", label: "Prezzi & Calendario", desc: "Tariffe e disponibilità", route: "/admin/prices" },
        { icon: "percent-outline", label: "Costi & tariffe", desc: "Commissioni Booking.com", route: "/admin/commissions" },
        { icon: "ticket-percent-outline", label: "Codici sconto", desc: "Sconti e sblocco mappa/IA", route: "/admin/discounts" },
        { icon: "image-multiple-outline", label: "Foto", desc: "Galleria pubblica e privata", route: "/admin/photos" },
        { icon: "silverware-fork-knife", label: "Cucina Siciliana", desc: "Foto, ingredienti, curiosità", route: "/admin/food" },
        { icon: "map-marker-multiple", label: "Mappa Interattiva", desc: "POI, coordinate, import/export", route: "/admin/map-pois" },
      ],
    },
    {
      title: "Carmelo · assistente",
      tiles: [
        { icon: "comment-question-outline", label: "Domande ospiti", desc: "Messaggi ricevuti", route: "/admin/questions" },
        { icon: "frequently-asked-questions", label: "FAQ", desc: "Domande frequenti", route: "/admin/faqs" },
        { icon: "robot-happy-outline", label: "Carmelo IA", desc: "Assistente itinerari", route: "/(guest)/itineraries" },
      ],
    },
    {
      title: "Marketing & notifiche",
      tiles: [
        { icon: "bullhorn-outline", label: "Marketing AI", desc: "Genera post e contenuti", route: "/admin/marketing" },
        { icon: "google", label: "Google Business", desc: "Recensioni e post GBP", route: "/admin/google-business" },
        { icon: "whatsapp", label: "WhatsApp", desc: "Notifiche prenotazioni", route: "/admin/whatsapp" },
      ],
    },
  ];

  return (
    <View style={s.screen}>
      <Header
        title="Dashboard"
        kicker="Admin"
        showLang={false}
        right={
          <Pressable
            testID="admin-logout"
            onPress={async () => {
              await logout();
              router.replace("/(guest)");
            }}
            style={s.logoutBtn}
            hitSlop={6}
          >
            <Icon name="logout" size={20} color={colors.error} />
          </Pressable>
        }
      />
      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["admin-stats"] })} tintColor={colors.brandPrimary} />}
      >
        {stats.isLoading ? (
          <Loading />
        ) : (
          <View style={s.kpiGrid}>
            {kpis.map((k) => (
              <Card key={k.label} style={s.kpiCard}>
                <View style={[s.kpiIcon, { backgroundColor: k.tint + "22" }]}>
                  <Icon name={k.icon} size={22} color={k.tint} />
                </View>
                <Text style={s.kpiVal}>{k.value}</Text>
                <Text style={s.kpiLabel}>{k.label}</Text>
              </Card>
            ))}
          </View>
        )}

        {sections.map((section) => (
          <View key={section.title}>
            <Text style={s.sectionTitle}>{section.title}</Text>
            <View style={{ gap: spacing.sm }}>
              {section.tiles.map((tile) => (
                <Pressable key={tile.label} testID={`tile-${tile.label}`} onPress={() => router.push(tile.route as any)}>
                  <Card style={s.tile}>
                    <View style={s.tileIcon}>
                      <Icon name={tile.icon} size={24} color={colors.brandPrimary} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.tileLabel}>{tile.label}</Text>
                      <Text style={s.tileDesc}>{tile.desc}</Text>
                    </View>
                    <Icon name="chevron-right" size={24} color={colors.muted} />
                  </Card>
                </Pressable>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  logoutBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: c.border },
  kpiGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  kpiCard: { flexGrow: 1, minWidth: "45%", alignItems: "flex-start", gap: 6 },
  kpiIcon: { width: 40, height: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  kpiVal: { color: c.onSurface, fontSize: 26, fontFamily: fonts.heading, marginTop: 4 },
  kpiLabel: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  sectionTitle: { color: c.onSurface, fontSize: 22, fontFamily: fonts.heading, marginTop: spacing.xl, marginBottom: spacing.md },
  tile: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  tileIcon: { width: 48, height: 48, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  tileLabel: { color: c.onSurface, fontSize: 16, fontFamily: fonts.heading },
  tileDesc: { color: c.muted, fontSize: 13, fontFamily: fonts.body, marginTop: 2 },
}));
