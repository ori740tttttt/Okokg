import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable, Modal, RefreshControl } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/src/components/Header";
import { Card, Field, Button, Loading, EmptyState, ChipRow, SectionTitle, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";
import { api } from "@/src/lib/api";
import { Poi } from "@/src/lib/queries";
import { downloadAuthedFile, uploadAuthedFile } from "@/src/lib/adminFiles";

const WORD = ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
const PDF = ["application/pdf"];
const CSV = ["text/csv", "text/comma-separated-values", "application/csv", "*/*"];

export default function AdminMapPois() {
  const s = useStyles();
  const { colors } = useTheme();
  const { token, loading } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [cat, setCat] = useState("all");
  const [editing, setEditing] = useState<Partial<Poi> | null>(null);
  const [busy, setBusy] = useState(false);
  const [io, setIo] = useState(false);

  useEffect(() => {
    if (!loading && !token) router.replace("/admin/login");
  }, [loading, token]);

  const pois = useQuery({
    queryKey: ["pois"],
    enabled: !!token,
    queryFn: async () => (await api.get<Poi[]>("/pois")).data,
  });

  const list = useMemo(() => {
    const all = pois.data ?? [];
    return cat === "all" ? all : all.filter((p) => p.category === cat);
  }, [pois.data, cat]);

  const chips = [
    { key: "all", label: `Tutti (${(pois.data ?? []).length})`, icon: "map-marker-multiple" as const },
    { key: "art", label: "Arte", icon: "bank" as const },
    { key: "beach", label: "Spiagge", icon: "beach" as const },
    { key: "nature", label: "Natura", icon: "pine-tree" as const },
  ];

  const save = async () => {
    if (!editing?.name?.trim()) return toast.show("Nome obbligatorio", "error");
    const lat = parseFloat(String(editing.lat));
    const lng = parseFloat(String(editing.lng));
    if (Number.isNaN(lat) || Number.isNaN(lng)) return toast.show("Coordinate non valide", "error");
    setBusy(true);
    const payload = {
      name: editing.name.trim(),
      category: editing.category || "art",
      lat,
      lng,
      town: editing.town || null,
      province: editing.province || null,
      description: editing.description || null,
      price: editing.price || null,
      hours: editing.hours || null,
      duration: editing.duration || null,
      discount: editing.discount || null,
      notes: editing.notes || null,
      ticket_url: editing.ticket_url || null,
      maps_url: editing.maps_url || null,
      image_url: editing.image_url || null,
    };
    try {
      if (editing.id) await api.put(`/pois/${editing.id}`, payload);
      else await api.post("/pois", payload);
      toast.show("Attrazione salvata", "success");
      qc.invalidateQueries({ queryKey: ["pois"] });
      setEditing(null);
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/pois/${id}`);
      qc.invalidateQueries({ queryKey: ["pois"] });
      toast.show("Eliminata", "success");
    } catch (e: any) {
      toast.show(e?.response?.data?.detail || "Errore", "error");
    }
  };

  const exportFile = async (path: string, filename: string) => {
    if (!token) return;
    setIo(true);
    try {
      await downloadAuthedFile(path, filename, token);
      toast.show("File esportato", "success");
    } catch (e: any) {
      toast.show(e?.message || "Errore export", "error");
    } finally {
      setIo(false);
    }
  };

  const importFile = async (path: string, accept: string[]) => {
    if (!token) return;
    setIo(true);
    try {
      const res = await uploadAuthedFile(path, token, accept);
      if (res) {
        qc.invalidateQueries({ queryKey: ["pois"] });
        toast.show(`Importate: ${res.created ?? 0} nuove, ${res.updated ?? 0} aggiornate`, "success");
      }
    } catch (e: any) {
      toast.show(e?.message || "Errore import", "error");
    } finally {
      setIo(false);
    }
  };

  if (loading || !token) return <Loading />;

  return (
    <View style={s.screen}>
      <Header
        title="Mappa Interattiva"
        kicker="Admin"
        showBack
        showLang={false}
        right={
          <Pressable testID="poi-add-btn" onPress={() => setEditing({ category: "art", province: "PA" })} hitSlop={6} style={s.addBtn}>
            <Icon name="plus" size={22} color={colors.onBrandPrimary} />
          </Pressable>
        }
      />

      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={false} onRefresh={() => qc.invalidateQueries({ queryKey: ["pois"] })} tintColor={colors.brandPrimary} />}
      >
        <View style={{ padding: spacing.md }}>
          <Card style={{ gap: spacing.sm }}>
            <SectionTitle title="Compila offline · Import / Export" />
            <Text style={s.hint}>Scarica le schede (Word/PDF con nome e coordinate già inseriti), compilale e reimportale. I campi vuoti non sovrascrivono i dati esistenti.</Text>
            <View style={s.ioRow}>
              <IoBtn testID="exp-word" icon="file-word-box" label="Word" onPress={() => exportFile("/pois/export-docx", "schede_attrazioni.docx")} c={colors} s={s} />
              <IoBtn testID="exp-pdf" icon="file-pdf-box" label="PDF" onPress={() => exportFile("/pois/export-pdf", "schede_attrazioni.pdf")} c={colors} s={s} />
              <IoBtn testID="exp-csv" icon="file-delimited-outline" label="CSV" onPress={() => exportFile("/pois/export", "attrazioni.csv")} c={colors} s={s} />
              <IoBtn testID="exp-tpl" icon="file-outline" label="Template" onPress={() => exportFile("/pois/template", "template_attrazioni.csv")} c={colors} s={s} />
            </View>
            <View style={s.ioRow}>
              <IoBtn testID="imp-word" icon="upload" label="Imp. Word" onPress={() => importFile("/pois/import-docx", WORD)} c={colors} s={s} />
              <IoBtn testID="imp-pdf" icon="upload" label="Imp. PDF" onPress={() => importFile("/pois/import-pdf", PDF)} c={colors} s={s} />
              <IoBtn testID="imp-csv" icon="upload" label="Imp. CSV" onPress={() => importFile("/pois/import", CSV)} c={colors} s={s} />
            </View>
            {io ? <Text style={s.ioBusy}>Operazione in corso…</Text> : null}
          </Card>
        </View>

        <ChipRow items={chips} selected={cat} onSelect={setCat} />

        <View style={{ padding: spacing.md, gap: spacing.sm }}>
          {pois.isLoading ? (
            <Loading />
          ) : list.length === 0 ? (
            <EmptyState icon="map-marker-off-outline" title="Nessuna attrazione" subtitle="Tocca + per aggiungere un punto." />
          ) : (
            list.map((p) => (
              <Card key={p.id} testID={`poi-${p.id}`} style={s.item}>
                <View style={{ flex: 1 }}>
                  <Text style={s.itemName}>{p.name}</Text>
                  <Text style={s.itemMeta}>{p.town ?? "—"} · {p.province ?? "—"} · {p.lat.toFixed(4)},{p.lng.toFixed(4)}</Text>
                  {!p.description ? <Text style={s.incomplete}>scheda da completare</Text> : null}
                </View>
                <Pressable testID={`poi-edit-${p.id}`} onPress={() => setEditing(p)} hitSlop={6} style={s.iconBtn}>
                  <Icon name="pencil-outline" size={18} color={colors.brandPrimary} />
                </Pressable>
                <Pressable testID={`poi-del-${p.id}`} onPress={() => remove(p.id)} hitSlop={6} style={s.iconBtn}>
                  <Icon name="trash-can-outline" size={18} color={colors.error} />
                </Pressable>
              </Card>
            ))
          )}
        </View>
      </ScrollView>

      <Modal visible={!!editing} transparent animationType="slide" onRequestClose={() => setEditing(null)}>
        <Pressable style={s.backdrop} onPress={() => setEditing(null)}>
          <Pressable style={s.sheet} onPress={(e) => e.stopPropagation()}>
            <KeyboardAwareScrollView bottomOffset={20} showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
              <Text style={s.sheetTitle}>{editing?.id ? "Modifica attrazione" : "Nuova attrazione"}</Text>
              <Field value={editing?.name || ""} onChangeText={(v) => setEditing((e) => ({ ...e, name: v }))} placeholder="Nome attrazione" icon="map-marker" testID="f-name" />
              <ChipRow
                items={[{ key: "art", label: "Arte" }, { key: "beach", label: "Spiaggia" }, { key: "nature", label: "Natura" }]}
                selected={editing?.category || "art"}
                onSelect={(k) => setEditing((e) => ({ ...e, category: k as any }))}
              />
              <View style={s.row2}>
                <View style={{ flex: 1 }}>
                  <Field value={editing?.lat != null ? String(editing.lat) : ""} onChangeText={(v) => setEditing((e) => ({ ...e, lat: v as any }))} placeholder="Latitudine" icon="latitude" keyboardType="numeric" testID="f-lat" />
                </View>
                <View style={{ flex: 1 }}>
                  <Field value={editing?.lng != null ? String(editing.lng) : ""} onChangeText={(v) => setEditing((e) => ({ ...e, lng: v as any }))} placeholder="Longitudine" icon="longitude" keyboardType="numeric" testID="f-lng" />
                </View>
              </View>
              <Text style={s.tip}>Tip: su Google Maps, click destro sul punto e copia i numeri (es. 38.0820, 13.2397).</Text>
              <View style={s.row2}>
                <View style={{ flex: 1 }}>
                  <Field value={editing?.town || ""} onChangeText={(v) => setEditing((e) => ({ ...e, town: v }))} placeholder="Comune" icon="city" testID="f-town" />
                </View>
                <ChipRow items={[{ key: "PA", label: "PA" }, { key: "TP", label: "TP" }]} selected={editing?.province || "PA"} onSelect={(k) => setEditing((e) => ({ ...e, province: k }))} />
              </View>
              <Field value={editing?.description || ""} onChangeText={(v) => setEditing((e) => ({ ...e, description: v }))} placeholder="Descrizione breve" icon="text" multiline testID="f-desc" />
              <View style={s.row2}>
                <View style={{ flex: 1 }}><Field value={editing?.price || ""} onChangeText={(v) => setEditing((e) => ({ ...e, price: v }))} placeholder="Prezzo (es. €6)" icon="cash" testID="f-price" /></View>
                <View style={{ flex: 1 }}><Field value={editing?.hours || ""} onChangeText={(v) => setEditing((e) => ({ ...e, hours: v }))} placeholder="Orari" icon="clock-outline" testID="f-hours" /></View>
              </View>
              <View style={s.row2}>
                <View style={{ flex: 1 }}><Field value={editing?.duration || ""} onChangeText={(v) => setEditing((e) => ({ ...e, duration: v }))} placeholder="Durata (es. 2-3 ore)" icon="timer-sand" testID="f-duration" /></View>
                <View style={{ flex: 1 }}><Field value={editing?.discount || ""} onChangeText={(v) => setEditing((e) => ({ ...e, discount: v }))} placeholder="Sconti" icon="sale" testID="f-discount" /></View>
              </View>
              <Field value={editing?.notes || ""} onChangeText={(v) => setEditing((e) => ({ ...e, notes: v }))} placeholder="Note (opzionale)" icon="information-outline" multiline testID="f-notes" />
              <Field value={editing?.ticket_url || ""} onChangeText={(v) => setEditing((e) => ({ ...e, ticket_url: v }))} placeholder="Link biglietti (https://...)" icon="ticket-confirmation-outline" autoCapitalize="none" testID="f-ticket" />
              <Field value={editing?.maps_url || ""} onChangeText={(v) => setEditing((e) => ({ ...e, maps_url: v }))} placeholder="Link Google Maps indicazioni" icon="directions" autoCapitalize="none" testID="f-maps" />
              <Field value={editing?.image_url || ""} onChangeText={(v) => setEditing((e) => ({ ...e, image_url: v }))} placeholder="Link foto (https://...)" icon="image-outline" autoCapitalize="none" testID="f-image" />
              <Button testID="poi-save" label="Salva attrazione" icon="content-save" onPress={save} loading={busy} />
            </KeyboardAwareScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function IoBtn({ icon, label, onPress, c, s, testID }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} style={s.ioBtn}>
      <Icon name={icon} size={20} color={c.brandPrimary} />
      <Text style={s.ioBtnTxt}>{label}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  addBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  hint: { color: c.muted, fontSize: 12, fontFamily: fonts.body, lineHeight: 17 },
  ioRow: { flexDirection: "row", gap: spacing.sm },
  ioBtn: { flex: 1, alignItems: "center", gap: 4, backgroundColor: c.surfaceTertiary, borderRadius: radius.md, paddingVertical: spacing.sm },
  ioBtnTxt: { color: c.onSurface, fontSize: 11, fontFamily: fonts.body },
  ioBusy: { color: c.brand, fontSize: 12, fontFamily: fonts.body, textAlign: "center" },
  item: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  itemName: { color: c.onSurface, fontSize: 15, fontFamily: fonts.heading },
  itemMeta: { color: c.muted, fontSize: 11, fontFamily: fonts.body, marginTop: 2 },
  incomplete: { color: c.warning, fontSize: 11, fontFamily: fonts.body, marginTop: 2 },
  iconBtn: { padding: 6 },
  backdrop: { flex: 1, backgroundColor: "rgba(44,42,40,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, maxHeight: "90%" },
  sheetTitle: { color: c.onSurface, fontSize: 20, fontFamily: fonts.heading, marginBottom: 4 },
  row2: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  tip: { color: c.muted, fontSize: 11, fontFamily: fonts.body, marginTop: -2 },
}));
