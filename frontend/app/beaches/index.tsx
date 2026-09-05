import React, { useMemo, useState } from "react";
import { View, Text, Pressable, FlatList, Linking } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { ChipRow, Field, Loading } from "@/src/components/ui";
import { Icon, IconName } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { beaches, windFromDegrees, analyzeBeach, Beach, BeachStatus } from "@/src/lib/beaches";
import i18n from "@/src/i18n";

type Weather = { temp: number; windSpeed: number; windName: string; windLabel: string; uv: number; sunset: string };

async function fetchWeather(): Promise<Weather> {
  const res = await fetch(
    "https://api.open-meteo.com/v1/forecast?latitude=38.0667&longitude=13.0333&current_weather=true&daily=sunset,uv_index_max&timezone=Europe%2FRome",
  );
  const data = await res.json();
  const w = windFromDegrees(data.current_weather.winddirection);
  return {
    temp: Math.round(data.current_weather.temperature),
    windSpeed: Math.round(data.current_weather.windspeed),
    windName: w.name,
    windLabel: w.label,
    uv: data.daily?.uv_index_max?.[0] ?? 6,
    sunset: data.daily?.sunset?.[0]?.split("T")[1] ?? "20:15",
  };
}

const NORTH = ["Tramontana", "Grecale", "Maestrale"];
const SOUTH = ["Scirocco", "Ostro", "Libeccio"];

export default function BeachesScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const lang = i18n.language === "en" ? "en" : "it";
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");

  const weather = useQuery({ queryKey: ["beach-weather"], queryFn: fetchWeather, staleTime: 10 * 60 * 1000 });
  const w = weather.data;
  const windName = w?.windName ?? "";

  const advice = useMemo(() => {
    if (!windName) return { rec: "", avoid: "" };
    if (NORTH.includes(windName))
      return {
        rec: `Oggi soffia vento da NORD (${w!.windLabel}). Punta sulla Costa Sud (Mazara, Selinunte, Tre Fontane) o calette riparate: mare piatto e calmo!`,
        avoid: "Evita la costa Nord esposta (Trappeto, Balestrate, Cefalù): mare mosso, onde e possibili alghe a riva.",
      };
    if (SOUTH.includes(windName))
      return {
        rec: `Oggi vento da SUD (${w!.windLabel}). Giornata perfetta vicino casa! La costa Nord (Trappeto, Balestrate, Terrasini) avrà acqua calma e cristallina.`,
        avoid: "Attenzione alla Costa Sud (Mazara, Campobello): il mare spinge da fuori e porta moto ondoso.",
      };
    return {
      rec: `Vento laterale di ${w!.windLabel}. Scegli le spiagge protette dai promontori per goderti la giornata.`,
      avoid: `Evita le coste direttamente esposte a ${w!.windLabel}.`,
    };
  }, [windName, w]);

  const chips: { key: string; label: string; icon: IconName }[] = [
    { key: "all", label: "Tutte", icon: "beach" },
    { key: "kids", label: "Bambini", icon: "baby-face-outline" },
    { key: "lidi", label: "Attrezzate", icon: "umbrella-outline" },
    { key: "snorkel", label: "Snorkel", icon: "diving-snorkel" },
    { key: "park", label: "Parcheggio", icon: "parking" },
    { key: "park_free", label: "Park Gratis", icon: "cash-off" },
  ];

  const filtered = useMemo(() => {
    let list = [...beaches];
    if (cat === "park_free") list = list.filter((b) => b.parking_type === "free");
    else if (cat !== "all") list = list.filter((b) => (b as any)[cat] === true);
    if (q.trim()) {
      const needle = q.toLowerCase();
      list = list.filter(
        (b) => b.name.toLowerCase().includes(needle) || b.location.toLowerCase().includes(needle) || b.prov.toLowerCase().includes(needle),
      );
    }
    if (windName) {
      const score: Record<BeachStatus, number> = { recommended: 1, neutral: 2, avoid: 3 };
      list.sort((a, b) => score[analyzeBeach(a, windName)] - score[analyzeBeach(b, windName)]);
    }
    return list;
  }, [cat, q, windName]);

  const statusMeta = (st: BeachStatus) => {
    if (st === "recommended") return { color: colors.success, label: "✨ IDEALE OGGI" };
    if (st === "avoid") return { color: colors.error, label: "⚠️ MARE MOSSO" };
    return { color: colors.muted, label: "🌤️ ACCETTABILE" };
  };

  const parkingBadge = (type: Beach["parking_type"]) => {
    if (type === "free") return { color: colors.success, label: "🆓 Gratis" };
    if (type === "paid") return { color: colors.warning, label: "🪙 A pagamento" };
    return { color: colors.info, label: "⚖️ Misto / Strisce blu" };
  };

  const openDir = (b: Beach) =>
    Linking.openURL(`https://www.google.com/maps/dir/?api=1&origin=Trappeto,PA&destination=${b.lat},${b.lng}`).catch(() => {});

  const renderItem = ({ item }: { item: Beach }) => {
    const bl = item[lang];
    const st = windName ? analyzeBeach(item, windName) : "neutral";
    const meta = statusMeta(st);
    const pk = parkingBadge(item.parking_type);
    const ferry = item.dist.toLowerCase().includes("aliscafo");
    const tags: { icon: IconName; on: boolean }[] = [
      { icon: "baby-face-outline", on: item.kids },
      { icon: "umbrella-outline", on: item.lidi },
      { icon: "diving-snorkel", on: item.snorkel },
      { icon: "parking", on: item.park },
    ];
    return (
      <View style={s.card}>
        <View style={s.cardHead}>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{item.name}</Text>
            <View style={s.metaRow}>
              <Icon name={ferry ? "ferry" : "car"} size={13} color={colors.olive} />
              <Text style={s.metaTxt}>
                {item.location} ({item.prov}) · {item.time} ({item.dist})
              </Text>
            </View>
          </View>
          <View style={[s.statusPill, { backgroundColor: meta.color + "22" }]}>
            <Text style={[s.statusTxt, { color: meta.color }]}>{meta.label}</Text>
          </View>
        </View>

        <Text style={s.desc}>{bl.desc}</Text>

        <View style={s.infoBox}>
          <View style={s.infoLine}>
            <Text style={s.infoKey}>Parcheggio</Text>
            <View style={[s.pkBadge, { backgroundColor: pk.color + "22" }]}>
              <Text style={[s.pkTxt, { color: pk.color }]}>{pk.label}</Text>
            </View>
          </View>
          <Text style={s.infoVal}>{bl.parking_info}</Text>
          <View style={s.infoGrid}>
            <Text style={s.infoSmall}>👥 {bl.crowd}</Text>
            <Text style={s.infoSmall}>🍹 {bl.food}</Text>
            <Text style={s.infoSmall}>🌊 {bl.seabed}</Text>
          </View>
        </View>

        {bl.tips ? (
          <View style={s.tip}>
            <Icon name="lightbulb-on-outline" size={14} color={colors.brand} />
            <Text style={s.tipTxt}>{bl.tips}</Text>
          </View>
        ) : null}

        <View style={s.cardFoot}>
          <View style={s.tags}>
            {tags.filter((tg) => tg.on).map((tg, i) => (
              <Icon key={i} name={tg.icon} size={18} color={colors.oliveSoft} />
            ))}
          </View>
          <Pressable testID={`beach-dir-${item.id}`} onPress={() => openDir(item)} style={s.dirBtn}>
            <Icon name="directions" size={16} color={colors.onBrandPrimary} />
            <Text style={s.dirTxt}>Portami lì</Text>
          </Pressable>
        </View>
      </View>
    );
  };

  return (
    <View style={s.screen}>
      <Header title="Spiagge" kicker="Bussola dei venti" showBack />
      <FlatList
        testID="beaches-list"
        data={filtered}
        keyExtractor={(b) => b.id}
        renderItem={renderItem}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingBottom: spacing.xxl, gap: spacing.md }}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={
          <View>
            {/* Live weather */}
            <View style={s.weatherWrap}>
              <LinearGradient colors={[colors.brandPrimary, colors.olive]} style={s.weatherBg} />
              {weather.isLoading ? (
                <View style={{ padding: spacing.lg }}>
                  <Loading label="Meteo in tempo reale..." />
                </View>
              ) : (
                <View style={s.weatherRow}>
                  <WeatherCell icon="🌡️" label="Temp" value={`${w?.temp ?? "--"}°`} />
                  <WeatherCell icon="🌬️" label="Vento" value={w?.windName ?? "--"} sub={`${w?.windSpeed ?? "--"} km/h`} />
                  <WeatherCell icon="☀️" label="UV" value={`${w?.uv ?? "--"}`} />
                  <WeatherCell icon="🌅" label="Tramonto" value={w?.sunset ?? "--"} />
                </View>
              )}
            </View>

            {/* Advice */}
            {w ? (
              <View style={s.adviceWrap}>
                <View style={[s.advice, { backgroundColor: colors.success + "18", borderColor: colors.success }]}>
                  <Text style={[s.adviceTitle, { color: colors.success }]}>✨ Consigliate oggi</Text>
                  <Text style={s.adviceTxt}>{advice.rec}</Text>
                </View>
                <View style={[s.advice, { backgroundColor: colors.error + "14", borderColor: colors.error }]}>
                  <Text style={[s.adviceTitle, { color: colors.error }]}>⚠️ Da evitare</Text>
                  <Text style={s.adviceTxt}>{advice.avoid}</Text>
                </View>
              </View>
            ) : null}

            <View style={{ paddingHorizontal: spacing.md, paddingTop: spacing.sm }}>
              <Field value={q} onChangeText={setQ} placeholder="Cerca (San Vito, Cefalù, Mondello...)" icon="magnify" testID="beach-search" />
            </View>
            <ChipRow items={chips} selected={cat} onSelect={setCat} />
            <Text style={s.count}>{filtered.length} spiagge</Text>
          </View>
        }
      />
    </View>
  );
}

function WeatherCell({ icon, label, value, sub }: { icon: string; label: string; value: string; sub?: string }) {
  const s = useStyles();
  return (
    <View style={s.wCell}>
      <Text style={s.wLabel}>{label.toUpperCase()}</Text>
      <Text style={s.wValue}>
        {icon} {value}
      </Text>
      {sub ? <Text style={s.wSub}>{sub}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  weatherWrap: { margin: spacing.md, borderRadius: radius.lg, overflow: "hidden", minHeight: 92 },
  weatherBg: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  weatherRow: { flexDirection: "row", padding: spacing.md, gap: spacing.sm },
  wCell: { flex: 1, alignItems: "center" },
  wLabel: { color: "rgba(255,255,255,0.8)", fontSize: 9, letterSpacing: 1, fontFamily: fonts.body, fontWeight: "700" },
  wValue: { color: "#fff", fontSize: 15, fontFamily: fonts.heading, marginTop: 4, textAlign: "center" },
  wSub: { color: "rgba(255,255,255,0.85)", fontSize: 11, fontFamily: fonts.body },
  adviceWrap: { paddingHorizontal: spacing.md, gap: spacing.sm },
  advice: { borderRadius: radius.md, borderWidth: 1, borderLeftWidth: 4, padding: spacing.md },
  adviceTitle: { fontSize: 13, fontWeight: "800", fontFamily: fonts.body, marginBottom: 4 },
  adviceTxt: { color: c.onSurfaceSecondary, fontSize: 13, lineHeight: 19, fontFamily: fonts.body },
  count: { color: c.muted, fontSize: 12, fontFamily: fonts.body, paddingHorizontal: spacing.md, textTransform: "uppercase", letterSpacing: 1 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border, padding: spacing.md, marginHorizontal: spacing.md, gap: spacing.sm },
  cardHead: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  name: { color: c.onSurface, fontSize: 18, fontFamily: fonts.heading },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  metaTxt: { color: c.muted, fontSize: 11, fontFamily: fonts.body, flexShrink: 1 },
  statusPill: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: radius.pill },
  statusTxt: { fontSize: 10, fontWeight: "800", fontFamily: fonts.body },
  desc: { color: c.onSurfaceSecondary, fontSize: 14, lineHeight: 20, fontFamily: fonts.body },
  infoBox: { backgroundColor: c.surfaceTertiary, borderRadius: radius.md, padding: spacing.sm, gap: 4 },
  infoLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  infoKey: { color: c.onSurface, fontSize: 12, fontWeight: "700", fontFamily: fonts.body },
  pkBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  pkTxt: { fontSize: 11, fontWeight: "700", fontFamily: fonts.body },
  infoVal: { color: c.onSurfaceSecondary, fontSize: 12, lineHeight: 17, fontFamily: fonts.body },
  infoGrid: { gap: 2, marginTop: 2 },
  infoSmall: { color: c.onSurfaceTertiary, fontSize: 12, fontFamily: fonts.body },
  tip: { flexDirection: "row", gap: 6, backgroundColor: c.terracottaSoft, padding: spacing.sm, borderRadius: radius.md },
  tipTxt: { color: c.onSurfaceSecondary, fontSize: 12, fontStyle: "italic", flex: 1, fontFamily: fonts.body },
  cardFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderTopWidth: 1, borderTopColor: c.divider, paddingTop: spacing.sm },
  tags: { flexDirection: "row", gap: spacing.sm },
  dirBtn: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: c.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill },
  dirTxt: { color: c.onBrandPrimary, fontSize: 13, fontWeight: "600", fontFamily: fonts.body },
}));
