import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import * as Localization from "expo-localization";

import it from "./locales/it.json";
import en from "./locales/en.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import de from "./locales/de.json";

export const SUPPORTED_LANGUAGES = [
  { code: "it", label: "Italiano", flag: "🇮🇹" },
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "de", label: "Deutsch", flag: "🇩🇪" },
];

const SUPPORTED = ["it", "en", "es", "fr", "de"];

function deviceLanguage(): string {
  try {
    const locales = Localization.getLocales();
    const code = locales?.[0]?.languageCode ?? "it";
    return SUPPORTED.includes(code) ? code : "it";
  } catch {
    return "it";
  }
}

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources: {
      it: { translation: it },
      en: { translation: en },
      es: { translation: es },
      fr: { translation: fr },
      de: { translation: de },
    },
    lng: deviceLanguage(),
    fallbackLng: "it",
    supportedLngs: SUPPORTED,
    interpolation: { escapeValue: false },
    compatibilityJSON: "v4",
  });
}

export default i18n;
