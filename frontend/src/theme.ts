// Design tokens for this app. Light theme only.Always modify the colors and theme to Dark, Light or Dark and Light according to the design guidelines.
//
// The keys match the "color" block of /app/design_guidelines.json. Fill the
// values from that file (or from the user's brand colors). Keep every key; do
// not add a second theme or colors file; do not write color literals in
// components.
//
// How the names work: a plain key is a background, and its `on` partner is the
// text or icon color that sits on top of it. Always use them as a pair.
//   <View style={{ backgroundColor: colors.brandPrimary }}>
//     <Text style={{ color: colors.onBrandPrimary }}>Continue</Text>
//   </View>
//
// Styling a screen or component: build the sheet with makeStyles so colors
// and layout live together and follow the active scheme:
//   const useStyles = makeStyles((colors) => ({
//     card: { backgroundColor: colors.surfaceSecondary, padding: 16 },
//     title: { color: colors.onSurfaceSecondary, fontSize: 16 },
//   }));
//   function Screen() {
//     const styles = useStyles();
//     return <View style={styles.card}><Text style={styles.title}>Hi</Text></View>;
//   }
// For color props that are not styles (icon color, placeholderTextColor,
// ActivityIndicator) read useTheme().colors inside the component.
// Never call StyleSheet.create with color values at module level; it cannot
// follow the scheme.
//
// To support dark mode later: add `dark` to `themes` with every key filled.
// Nothing else changes; the device setting takes over automatically.
// Feel free to add as many new colors as you need to support the design guidelines.

import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  // Mediterranean palette — sand / terracotta / olive / ink
  surface: "#FAF8F5", // sand-50 canvas
  onSurface: "#2C2A28", // ink-900
  surfaceSecondary: "#FFFFFF", // cards, sheets, list rows
  onSurfaceSecondary: "#4A463F", // ink-700
  surfaceTertiary: "#F5F1E9", // sand-100 inputs, chips
  onSurfaceTertiary: "#6B6661", // ink-500
  surfaceInverse: "#2C2A28", // ink-900 popovers, snackbars
  onSurfaceInverse: "#FAF8F5",
  muted: "#8A857E", // subdued captions, placeholders

  brand: "#C67D63", // terracotta-500 identity
  onBrand: "#FFFFFF",
  brandPrimary: "#A6634A", // terracotta-600 primary CTA / active
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E6E2DB", // sand-200 secondary CTA
  onBrandSecondary: "#2C2A28",
  brandTertiary: "#F5F1E9", // sand-100 chips, tags
  onBrandTertiary: "#4A463F",

  // Olive accent (secondary brand hue from the original)
  olive: "#6E7E6A", // olive-600
  onOlive: "#FFFFFF",
  oliveSoft: "#8A9A86", // olive-500
  terracottaSoft: "#FBF1ED", // terracotta-50 tint

  success: "#4B7A52",
  onSuccess: "#FFFFFF",
  warning: "#B45309",
  onWarning: "#FFFFFF",
  error: "#A6463A",
  onError: "#FFFFFF",
  info: "#6E7E6A",
  onInfo: "#FFFFFF",

  border: "#E6E2DB", // sand-200 hairline
  borderStrong: "#CDC6B8", // sand-300 focus / selected
  divider: "#EDE8E0",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;

export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

// In-app theme toggle, only after `dark` exists in `themes`. Call
// setColorScheme("dark"), setColorScheme("light"), or setColorScheme(null) to
// follow the device. Every useTheme() consumer re-renders. Persisting the
// choice and re-applying it on launch is the toggle's job.
export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme);
}

// Keep native surfaces (alerts, pickers, navigation chrome) on the schemes this
// app ships: light only forces light; once `dark` exists the device decides.
// Optional call because react-native-web does not implement it.
setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = system && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

// Themed StyleSheet: returns a hook that builds the sheet from the active
// scheme's colors and memoizes it until the scheme changes.
export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}


