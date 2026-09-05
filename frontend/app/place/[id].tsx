import React from "react";
import { ScrollView, View, Text, Linking } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";

import { Header } from "@/src/components/Header";
import { Button, Card, EmptyState } from "@/src/components/ui";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { usePois } from "@/src/lib/queries";

export default function PlaceDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const pois = usePois();
  const poi = pois.data?.find((p) => p.id === id);

  if (!poi) {
    return (
      <View style={s.screen}>
        <Header title="—" showBack showLang={false} />
        <EmptyState icon="map-marker-off" title={t("map_page.no_results")} />
      </View>
    );
  }

  const openDirections = () => {
    const url = poi.maps_url || `https://www.google.com/maps/dir/?api=1&destination=${poi.lat},${poi.lng}`;
    Linking.openURL(url).catch(() => {});
  };

  const rows: { icon: IconName; label: string; value?: string }[] = [
    { icon: "cash", label: t("map_page.price"), value: poi.price },
    { icon: "clock-outline", label: t("map_page.hours"), value: poi.hours },
    { icon: "timer-sand", label: t("map_page.duration"), value: poi.duration },
    { icon: "tag-outline", label: t("map_page.discount"), value: poi.discount },
  ].filter((r) => r.value);

  return (
    <View style={s.screen}>
      <Header title={poi.name} showBack showLang={false} />
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxl }} showsVerticalScrollIndicator={false}>
        <View style={s.hero}>
          {poi.image_url ? (
            <Image source={{ uri: poi.image_url }} style={s.heroImg} contentFit="cover" />
          ) : (
            <View style={[s.heroImg, { backgroundColor: colors.olive, alignItems: "center", justifyContent: "center" }]}>
              <Icon name="image-off-outline" size={40} color={colors.onOlive} />
            </View>
          )}
          <LinearGradient colors={["transparent", "rgba(44,42,40,0.7)"]} style={s.heroOverlay} />
          <View style={s.heroContent}>
            <View style={s.catBadge}>
              <Text style={s.catTxt}>{t(`map_page.categories.${poi.category}`)}</Text>
            </View>
            <Text style={s.heroTitle}>{poi.name}</Text>
            <View style={s.metaRow}>
              <Icon name="map-marker" size={14} color="#fff" />
              <Text style={s.metaTxt}>{poi.town ?? poi.province ?? "Sicilia"}</Text>
            </View>
          </View>
        </View>

        <View style={s.body}>
          {poi.description ? <Text style={s.desc}>{poi.description}</Text> : null}
          {poi.notes ? (
            <Card style={{ marginTop: spacing.md, backgroundColor: colors.terracottaSoft, borderColor: colors.brandSecondary }}>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Icon name="lightbulb-on-outline" size={18} color={colors.brandPrimary} />
                <Text style={[s.desc, { flex: 1 }]}>{poi.notes}</Text>
              </View>
            </Card>
          ) : null}

          {rows.length > 0 ? (
            <Card style={{ marginTop: spacing.md, gap: spacing.sm }}>
              {rows.map((r) => (
                <View key={r.label} style={s.infoRow}>
                  <Icon name={r.icon} size={18} color={colors.olive} />
                  <Text style={s.infoLabel}>{r.label}</Text>
                  <Text style={s.infoVal}>{r.value}</Text>
                </View>
              ))}
            </Card>
          ) : null}

          <View style={{ marginTop: spacing.lg, gap: spacing.sm }}>
            <Button testID="place-directions" label={t("map_page.directions")} icon="directions" onPress={openDirections} />
            {poi.ticket_url ? (
              <Button
                testID="place-tickets"
                label={t("map_page.tickets")}
                icon="ticket-confirmation-outline"
                variant="outline"
                onPress={() => Linking.openURL(poi.ticket_url!).catch(() => {})}
              />
            ) : null}
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  hero: { height: 260 },
  heroImg: { width: "100%", height: "100%" },
  heroOverlay: { position: "absolute", left: 0, right: 0, bottom: 0, top: 0 },
  heroContent: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.md, gap: 6 },
  catBadge: { alignSelf: "flex-start", backgroundColor: c.brandPrimary, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  catTxt: { color: c.onBrandPrimary, fontSize: 11, fontWeight: "700", fontFamily: fonts.body },
  heroTitle: { color: "#fff", fontSize: 30, fontFamily: fonts.heading, lineHeight: 33 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  metaTxt: { color: "rgba(255,255,255,0.9)", fontSize: 13, fontFamily: fonts.body },
  body: { padding: spacing.md },
  desc: { color: c.onSurfaceSecondary, fontSize: 15, lineHeight: 23, fontFamily: fonts.body },
  infoRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  infoLabel: { color: c.muted, fontSize: 13, fontFamily: fonts.body, width: 70 },
  infoVal: { color: c.onSurface, fontSize: 14, fontFamily: fonts.body, flex: 1, fontWeight: "500" },
}));
