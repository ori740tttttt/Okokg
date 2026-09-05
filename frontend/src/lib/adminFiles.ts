import { Platform } from "react-native";
import * as Sharing from "expo-sharing";
import * as FileSystem from "expo-file-system/legacy";
import * as DocumentPicker from "expo-document-picker";
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

// Downloads an admin-protected file (GET) and saves/shares it natively or via browser on web.
export async function downloadAuthedFile(path: string, filename: string, token: string) {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error("Download non riuscito");
  const blob = await res.blob();

  if (Platform.OS === "web") {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return;
  }
  const base64 = await blobToBase64(blob);
  const uri = `${FileSystem.cacheDirectory}${filename}`;
  await FileSystem.writeAsStringAsync(uri, base64, { encoding: FileSystem.EncodingType.Base64 });
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri);
}

// Picks a document and uploads it to an admin-protected POST endpoint (multipart "file").
export async function uploadAuthedFile(path: string, token: string, accept: string[]): Promise<any | null> {
  const picked = await DocumentPicker.getDocumentAsync({ type: accept, copyToCacheDirectory: true, multiple: false });
  if (picked.canceled) return null;
  const asset = picked.assets[0];
  const form = new FormData();
  if ((asset as any).file) {
    form.append("file", (asset as any).file);
  } else {
    form.append("file", { uri: asset.uri, name: asset.name, type: asset.mimeType || "application/octet-stream" } as any);
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Import non riuscito");
  return data;
}
