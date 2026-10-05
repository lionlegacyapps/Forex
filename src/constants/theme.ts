import { DarkTheme, type Theme } from "@react-navigation/native";

export const palette = {
  background: "#0B1220",
  surface: "#141E30",
  surfaceElevated: "#1B263B",
  border: "#22324B",
  textPrimary: "#E2E8F0",
  textSecondary: "#94A3B8",
  green: "#22C55E",
  orange: "#F97316",
  red: "#EF4444",
  blue: "#3B82F6",
};

export const appTheme: Theme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    primary: palette.blue,
    background: palette.background,
    card: palette.surface,
    border: palette.border,
    text: palette.textPrimary,
    notification: palette.red,
  },
};
