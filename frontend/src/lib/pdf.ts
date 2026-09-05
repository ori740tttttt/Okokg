import { Platform } from "react-native";
import * as Sharing from "expo-sharing";
import * as FileSystem from "expo-file-system/legacy";
import { API_BASE } from "./api";

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const res = String(reader.result || "");
      resolve(res.includes(",") ? res.split(",")[1] : res);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// Requests the itinerary PDF from the backend (requires a valid unlock code) and
// saves/shares it natively, or triggers a browser download on web.
export async function downloadItineraryPdf(opts: { code: string; poiIds: string[]; travelerName?: string }) {
  const res = await fetch(`${API_BASE}/itinerary/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: opts.code, poi_ids: opts.poiIds, traveler_name: opts.travelerName || "" }),
  });
  if (!res.ok) {
    let detail = "Impossibile generare il PDF";
    try {
      detail = (await res.json())?.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  const blob = await res.blob();

  if (Platform.OS === "web") {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "itinerario-appartamento-matteo.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return;
  }

  const base64 = await blobToBase64(blob);
  const uri = `${FileSystem.cacheDirectory}itinerario-appartamento-matteo.pdf`;
  await FileSystem.writeAsStringAsync(uri, base64, { encoding: FileSystem.EncodingType.Base64 });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Il tuo itinerario" });
  }
}
