import React, { useMemo, useState } from "react";
import { ScrollView, View, Text, Pressable, RefreshControl, Modal } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Calendar } from "react-native-calendars";
import { useTranslation } from "react-i18next";
import { router } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import Animated, { FadeInDown } from "react-native-reanimated";

import { Header } from "@/src/components/Header";
import { Button, Card, SectionTitle, Loading } from "@/src/components/ui";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useProperty, usePhotos, useAvailability } from "@/src/lib/queries";
import { festivalDateSet, upcomingFestivals, Festival } from "@/src/lib/festivals";
import { euro, toISODate, nightsBetween } from "@/src/lib/format";

const HERO_IMG =
  "https://customer-assets.emergentagent.com/job_appart-app/artifacts/o3l6t9b1_Trappeto_borgo_marinaro_sicilia_occidentale_italy.jpg";

export default function HomeScreen() {
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();

  const property = useProperty();
  const photos = usePhotos();
  const availability = useAvailability();

  const [range, setRange] = useState<{ start: string | null; end: string | null }>({ start: null, end: null });
  const [festPopup, setFestPopup] = useState<Festival[] | null>(null);

  const av = availability.data;
  const blocked = useMemo(() => new Set(av?.blocked_dates ?? []), [av]);

  const markedDates = useMemo(() => {
    const marks: Record<string, any> = {};
    for (const d of blocked) {
      marks[d] = { disabled: true, disableTouchEvent: true, marked: true, dotColor: colors.error };
    }
    if (range.start) {
      marks[range.start] = {
        ...(marks[range.start] || {}),
        startingDay: true,
        color: colors.brandPrimary,
        textColor: colors.onBrandPrimary,
      };
    }
    if (range.start && range.end) {
      let cur = new Date(range.start);
      const end = new Date(range.end);
      while (cur <= end) {
        const iso = toISODate(cur);
        marks[iso] = {
          ...(marks[iso] || {}),
          color: colors.brandPrimary,
          textColor: colors.onBrandPrimary,
          startingDay: iso === range.start,
          endingDay: iso === range.end,
        };
        cur.setDate(cur.getDate() + 1);
      }
    }
    return marks;
  }, [blocked, range, colors]);

  const festMap = useMemo(() => festivalDateSet(), []);
  const markedWithFestivals = useMemo(() => {
    const marks = { ...markedDates };
    Object.keys(festMap).forEach((iso) => {
      const existing = marks[iso];
      if (!existing || (!existing.color && !existing.disabled)) {
        marks[iso] = { ...(existing || {}), marked: true, dotColor: colors.olive };
      }
    });
    return marks;
  }, [markedDates, festMap, colors]);

  const nextFestivals = useMemo(() => upcomingFestivals().slice(0, 3), []);

  const selectDay = (d: string) => {
    if (blocked.has(d)) return;
    if (!range.start || (range.start && range.end)) {
      setRange({ start: d, end: null });
    } else if (d > range.start) {
      setRange({ start: range.start, end: d });
    } else {
      setRange({ start: d, end: null });
    }
  };

  const onDayPress = (day: { dateString: string }) => {
    const d = day.dateString;
    const fests = festMap[d];
    if (fests && fests.length > 0) {
      setFestPopup(fests);
      return;
    }
    selectDay(d);
  };

  const nights = nightsBetween(range.start, range.end);

  const onRefresh = () => {
    qc.invalidateQueries({ queryKey: ["property"] });
    qc.invalidateQueries({ queryKey: ["photos"] });
    qc.invalidateQueries({ queryKey: ["availability"] });
  };

  const features: { icon: IconName; label: string; value: number }[] = property.data
    ? [
        { icon: "bed-king-outline", label: t("property.feature_rooms"), value: property.data.rooms },
        { icon: "shower", label: t("property.feature_bathrooms"), value: property.data.bathrooms },
        { icon: "silverware-fork-knife", label: t("property.feature_kitchen"), value: property.data.kitchen },
        { icon: "sofa-outline", label: t("property.feature_living"), value: property.data.living_room },
        { icon: "account-group-outline", label: t("property.feature_max_guests"), value: property.data.max_guests },
      ]
    : [];

  return (
    <View style={s.screen}>
      <Header title={property.data?.name ?? "Appartamento Matteo"} kicker={t("hero.kicker")} />
      <ScrollView
        testID="home-scroll"
        contentContainerStyle={{ paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      >
        {/* Hero */}
        <View style={s.hero}>
          <Image source={{ uri: HERO_IMG }} style={s.heroImg} contentFit="cover" transition={300} />
          <LinearGradient colors={["rgba(44,42,40,0.1)", "rgba(44,42,40,0.75)"]} style={s.heroOverlay} />
          <View style={s.heroContent}>
            <Text style={s.heroTitle}>
              {t("hero.title_line1")} {t("hero.title_line2")}
            </Text>
            <Text style={s.heroSub}>{t("hero.subtitle")}</Text>
          </View>
        </View>

        <View style={s.body}>
          {/* Booking CTA card */}
          <Animated.View entering={FadeInDown.delay(80)}>
            <Card style={{ marginTop: -spacing.xl }}>
              <View style={s.priceRow}>
                <View>
                  <Text style={s.priceKicker}>{t("booking.from")}</Text>
                  <Text style={s.price}>
                    {euro(av?.base_price ?? 80)}
                    <Text style={s.perNight}> {t("booking.per_night")}</Text>
                  </Text>
                </View>
                <View style={s.badge}>
                  <Icon name="star" size={14} color={colors.onOlive} />
                  <Text style={s.badgeTxt}>Trappeto</Text>
                </View>
              </View>
              <Button
                testID="home-book-cta"
                label={
                  nights > 0
                    ? `${t("booking.submit")} · ${nights} ${nights === 1 ? t("booking.guest_one") : "notti"}`
                    : t("booking.title")
                }
                icon="calendar-check"
                onPress={() =>
                  router.push({
                    pathname: "/booking",
                    params: { start: range.start ?? "", end: range.end ?? "" },
                  })
                }
              />
            </Card>
          </Animated.View>

          {/* Property */}
          {property.isLoading ? (
            <Loading />
          ) : (
            <View style={s.section}>
              <SectionTitle kicker={t("property.kicker")} title={property.data?.name ?? ""} />
              <Text style={s.desc}>{property.data?.description}</Text>
              <View style={s.features}>
                {features.map((f) => (
                  <View key={f.label} style={s.feature}>
                    <Icon name={f.icon} size={22} color={colors.olive} />
                    <Text style={s.featureVal}>{f.value}</Text>
                    <Text style={s.featureLabel}>{f.label}</Text>
                  </View>
                ))}
              </View>
              <View style={s.amenities}>
                {property.data?.amenities.map((a) => (
                  <View key={a} style={s.amenityChip}>
                    <Icon name="check-circle-outline" size={14} color={colors.olive} />
                    <Text style={s.amenityTxt}>{a}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Gallery */}
          {photos.data && photos.data.length > 0 ? (
            <View style={s.section}>
              <SectionTitle title="Galleria" />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
                {photos.data.map((p) => (
                  <Image key={p.id} source={{ uri: p.data_url }} style={s.galleryImg} contentFit="cover" transition={200} />
                ))}
              </ScrollView>
            </View>
          ) : null}

          {/* Calendar */}
          <View style={s.section}>
            <SectionTitle kicker={t("calendar.kicker")} title={t("calendar.title")} />
            <Text style={s.help}>{t("calendar.help")}</Text>
            <Card style={{ padding: spacing.sm }}>
              <Calendar
                testID="availability-calendar"
                markingType="period"
                markedDates={markedWithFestivals}
                onDayPress={onDayPress}
                minDate={toISODate(new Date())}
                theme={{
                  calendarBackground: colors.surfaceSecondary,
                  monthTextColor: colors.onSurface,
                  textMonthFontFamily: fonts.heading,
                  textMonthFontSize: 18,
                  dayTextColor: colors.onSurface,
                  textDisabledColor: colors.border,
                  todayTextColor: colors.brandPrimary,
                  arrowColor: colors.brandPrimary,
                  textDayFontFamily: fonts.body,
                  textDayHeaderFontFamily: fonts.body,
                }}
              />
              <View style={s.legend}>
                <Legend color={colors.brandPrimary} label={t("calendar.selected")} />
                <Legend color={colors.error} label={t("calendar.booked")} />
                <Legend color={colors.olive} label="Feste & Sagre" />
              </View>
            </Card>

            {/* Feste nel periodo */}
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              {nextFestivals.map((f) => (
                <Pressable key={f.id} testID={`home-fest-${f.id}`} onPress={() => router.push("/festivals")}>
                  <View style={s.festRow}>
                    <Text style={s.festGlyph}>{f.icon}</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={s.festName} numberOfLines={1}>{f.name}</Text>
                      <Text style={s.festMeta} numberOfLines={1}>{f.dateLabel} · {f.place}</Text>
                    </View>
                    <Icon name="chevron-right" size={20} color={colors.muted} />
                  </View>
                </Pressable>
              ))}
            </View>
          </View>

          {/* Spiagge + Feste CTAs */}
          <View style={[s.section, { flexDirection: "row", gap: spacing.sm }]}>
            <Pressable testID="home-beaches-cta" style={s.miniCta} onPress={() => router.push("/beaches")}>
              <Icon name="beach" size={26} color={colors.info} />
              <Text style={s.miniCtaTitle}>Spiagge</Text>
              <Text style={s.miniCtaSub}>Bussola dei venti live</Text>
            </Pressable>
            <Pressable testID="home-festivals-cta" style={s.miniCta} onPress={() => router.push("/festivals")}>
              <Icon name="calendar-star" size={26} color={colors.brand} />
              <Text style={s.miniCtaTitle}>Feste & Sagre</Text>
              <Text style={s.miniCtaSub}>Eventi del territorio</Text>
            </Pressable>
          </View>

          {/* Food CTA */}
          <Pressable testID="home-food-cta" style={s.section} onPress={() => router.push("/food")}>
            <View style={s.foodCta}>
              <View style={s.foodGlyphs}>
                <Text style={s.foodGlyph}>🍝</Text>
                <Text style={s.foodGlyph}>🥠</Text>
                <Text style={s.foodGlyph}>🍕</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.foodKicker}>CUCINA SICILIANA</Text>
                <Text style={s.foodTitle}>Sapori di Palermo & Trapani</Text>
                <Text style={s.foodSub}>Scopri le specialità del territorio</Text>
              </View>
              <Icon name="chevron-right" size={26} color={colors.onBrandPrimary} />
            </View>
          </Pressable>

          {/* Map CTA */}
          <Pressable testID="home-map-cta" style={s.section} onPress={() => router.push("/(guest)/places")}>
            <View style={s.mapCta}>
              <Image
                source={{ uri: "https://upload.wikimedia.org/wikipedia/commons/e/e7/Trappeto-spiaggia.jpg" }}
                style={s.mapCtaImg}
                contentFit="cover"
              />
              <LinearGradient colors={["rgba(44,42,40,0.85)", "rgba(44,42,40,0.35)"]} style={s.mapCtaOverlay} />
              <View style={s.mapCtaContent}>
                <Text style={s.mapCtaKicker}>{t("map_cta.kicker").toUpperCase()}</Text>
                <Text style={s.mapCtaTitle}>{t("map_cta.title")}</Text>
                <View style={s.mapCtaBtn}>
                  <Text style={s.mapCtaBtnTxt}>{t("map_cta.open")}</Text>
                </View>
              </View>
            </View>
          </Pressable>
        </View>
      </ScrollView>

      {/* Festival popup */}
      <Modal visible={!!festPopup} transparent animationType="fade" onRequestClose={() => setFestPopup(null)}>
        <Pressable style={s.festBackdrop} onPress={() => setFestPopup(null)}>
          <Pressable style={s.festSheet} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              {(festPopup ?? []).map((f) => (
                <View key={f.id} style={s.festItem} testID={`fest-popup-${f.id}`}>
                  <View style={s.festHead}>
                    <Text style={s.fpGlyph}>{f.icon}</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={s.fpName}>{f.name}</Text>
                      <View style={s.festMetaRow}>
                        <Icon name="map-marker" size={13} color={colors.olive} />
                        <Text style={s.festPlace}>{f.place} ({f.province})</Text>
                      </View>
                    </View>
                  </View>
                  <View style={s.festDateBox}>
                    <Icon name="calendar-star" size={15} color={colors.brandPrimary} />
                    <Text style={s.festDateTxt}>{f.dateLabel}</Text>
                  </View>
                  <Text style={s.festDesc}>{f.description}</Text>
                  <View style={s.festCuriosity}>
                    <Icon name="information-outline" size={15} color={colors.brand} />
                    <Text style={s.festCuriosityTxt}>{f.curiosity}</Text>
                  </View>
                </View>
              ))}
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Button
                    testID="fest-popup-select"
                    label="Usa questa data"
                    icon="calendar-check"
                    variant="olive"
                    onPress={() => {
                      const d = festPopup?.[0]?.start;
                      setFestPopup(null);
                      if (d) selectDay(d);
                    }}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Button testID="fest-popup-all" label="Tutte le feste" icon="calendar-star" onPress={() => { setFestPopup(null); router.push("/festivals"); }} />
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  const s = useStyles();
  return (
    <View style={s.legendItem}>
      <View style={[s.legendDot, { backgroundColor: color }]} />
      <Text style={s.legendTxt}>{label}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  festBackdrop: { flex: 1, backgroundColor: "rgba(44,42,40,0.5)", justifyContent: "center", padding: spacing.lg },
  festSheet: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, maxHeight: "80%" },
  festItem: { marginBottom: spacing.md, gap: spacing.sm },
  festHead: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  fpGlyph: { fontSize: 30 },
  fpName: { color: c.onSurface, fontSize: 18, fontFamily: fonts.heading, lineHeight: 21 },
  festMetaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  festPlace: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  festDateBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.terracottaSoft, paddingHorizontal: spacing.sm, paddingVertical: 7, borderRadius: radius.md, alignSelf: "flex-start" },
  festDateTxt: { color: c.brandPrimary, fontSize: 13, fontWeight: "700", fontFamily: fonts.body },
  festDesc: { color: c.onSurfaceSecondary, fontSize: 14, lineHeight: 20, fontFamily: fonts.body },
  festCuriosity: { flexDirection: "row", gap: 6, backgroundColor: c.surfaceTertiary, padding: spacing.sm, borderRadius: radius.md },
  festCuriosityTxt: { color: c.onSurfaceSecondary, fontSize: 13, lineHeight: 18, flex: 1, fontStyle: "italic", fontFamily: fonts.body },
  hero: { height: 340, backgroundColor: c.surfaceInverse },
  heroImg: { width: "100%", height: "100%" },
  heroOverlay: { position: "absolute", left: 0, right: 0, bottom: 0, top: 0 },
  heroContent: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.xl },
  heroTitle: { color: "#FFFFFF", fontSize: 42, fontFamily: fonts.heading, lineHeight: 44 },
  heroSub: { color: "rgba(255,255,255,0.9)", fontSize: 14, marginTop: spacing.sm, fontFamily: fonts.body },
  body: { paddingHorizontal: spacing.md },
  priceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md },
  priceKicker: { color: c.muted, fontSize: 11, letterSpacing: 1, fontFamily: fonts.body, textTransform: "uppercase" },
  price: { color: c.onSurface, fontSize: 30, fontFamily: fonts.heading },
  perNight: { fontSize: 14, color: c.muted, fontFamily: fonts.body },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: c.olive, paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  badgeTxt: { color: c.onOlive, fontSize: 12, fontWeight: "700", fontFamily: fonts.body },
  section: { marginTop: spacing.xl },
  desc: { color: c.onSurfaceSecondary, fontSize: 15, lineHeight: 23, fontFamily: fonts.body },
  features: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  feature: {
    alignItems: "center",
    backgroundColor: c.surfaceSecondary,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    borderWidth: 1,
    borderColor: c.border,
    flexGrow: 1,
    minWidth: 90,
    gap: 2,
  },
  featureVal: { color: c.onSurface, fontSize: 20, fontFamily: fonts.heading, marginTop: 4 },
  featureLabel: { color: c.muted, fontSize: 11, fontFamily: fonts.body, textAlign: "center" },
  amenities: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  amenityChip: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: c.surfaceTertiary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill },
  amenityTxt: { color: c.onSurfaceTertiary, fontSize: 13, fontFamily: fonts.body },
  galleryImg: { width: 240, height: 170, borderRadius: radius.md, backgroundColor: c.surfaceTertiary },
  help: { color: c.muted, fontSize: 13, marginBottom: spacing.sm, fontFamily: fonts.body },
  legend: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm, paddingHorizontal: spacing.sm, paddingBottom: 4 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 12, height: 12, borderRadius: 6 },
  legendTxt: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  mapCta: { height: 200, borderRadius: radius.lg, overflow: "hidden" },
  mapCtaImg: { width: "100%", height: "100%" },
  foodCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: c.brandPrimary, borderRadius: radius.lg, padding: spacing.md },
  foodGlyphs: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center", flexDirection: "row", flexWrap: "wrap" },
  foodGlyph: { fontSize: 18 },
  foodKicker: { color: "rgba(255,255,255,0.85)", fontSize: 10, letterSpacing: 2, fontFamily: fonts.body },
  foodTitle: { color: "#fff", fontSize: 19, fontFamily: fonts.heading, marginTop: 2 },
  foodSub: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontFamily: fonts.body, marginTop: 2 },
  festRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: spacing.sm },
  festGlyph: { fontSize: 24, width: 40, height: 40, textAlign: "center", lineHeight: 40, backgroundColor: c.surfaceTertiary, borderRadius: radius.sm, overflow: "hidden" },
  festName: { color: c.onSurface, fontSize: 14, fontFamily: fonts.heading },
  festMeta: { color: c.muted, fontSize: 12, fontFamily: fonts.body, marginTop: 1 },
  miniCta: { flex: 1, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border, padding: spacing.md, gap: 4 },
  miniCtaTitle: { color: c.onSurface, fontSize: 16, fontFamily: fonts.heading, marginTop: 4 },
  miniCtaSub: { color: c.muted, fontSize: 12, fontFamily: fonts.body },
  mapCtaOverlay: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  mapCtaContent: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.md, gap: spacing.sm },
  mapCtaKicker: { color: "rgba(255,255,255,0.85)", fontSize: 10, letterSpacing: 2, fontFamily: fonts.body },
  mapCtaTitle: { color: "#FFFFFF", fontSize: 24, fontFamily: fonts.heading, lineHeight: 27 },
  mapCtaBtn: { alignSelf: "flex-start", backgroundColor: "#FFFFFF", paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill },
  mapCtaBtnTxt: { color: c.onSurface, fontWeight: "600", fontFamily: fonts.body },
}));
