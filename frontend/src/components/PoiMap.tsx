import React from "react";
import MapView, { Marker } from "react-native-maps";
import { StyleSheet } from "react-native";
import type { Poi } from "@/src/lib/queries";

// Native interactive map with POI pins. Tapping a pin opens its detail sheet.
export function PoiMap({
  pois,
  selectedIds,
  onPressPoi,
  tintFor,
}: {
  pois: Poi[];
  selectedIds: string[];
  onPressPoi: (p: Poi) => void;
  tintFor: (cat: string) => string;
}) {
  return (
    <MapView
      testID="poi-map"
      style={StyleSheet.absoluteFill}
      initialRegion={{
        latitude: 38.07,
        longitude: 12.98,
        latitudeDelta: 0.8,
        longitudeDelta: 0.8,
      }}
    >
      {pois.map((p) => (
        <Marker
          key={p.id}
          testID={`marker-${p.id}`}
          coordinate={{ latitude: p.lat, longitude: p.lng }}
          title={p.name}
          description={p.town ?? p.province ?? "Sicilia"}
          pinColor={selectedIds.includes(p.id) ? "#C8563B" : tintFor(p.category)}
          onPress={() => onPressPoi(p)}
        />
      ))}
    </MapView>
  );
}
