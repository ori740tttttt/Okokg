import { Platform } from "react-native";

// Elegant editorial look: serif display headings + clean sans body.
// Uses reliable system faces so nothing blocks app start in Expo Go.
export const fonts = {
  heading: Platform.select({ ios: "Georgia", android: "serif", default: "Georgia" }) as string,
  body: Platform.select({ ios: "System", android: "sans-serif", default: "System" }) as string,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 8,
  md: 14,
  lg: 22,
  xl: 30,
  pill: 999,
};
