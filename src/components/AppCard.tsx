import { type PropsWithChildren } from "react";
import { StyleSheet, Text, View } from "react-native";

import { palette } from "@/constants/theme";

type AppCardProps = PropsWithChildren<{
  title?: string;
  description?: string;
}>;

export const AppCard = ({ title, description, children }: AppCardProps) => (
  <View style={styles.card}>
    {title ? <Text style={styles.title}>{title}</Text> : null}
    {description ? <Text style={styles.description}>{description}</Text> : null}
    {children}
  </View>
);

const styles = StyleSheet.create({
  card: {
    backgroundColor: palette.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 14,
    gap: 10,
  },
  title: {
    color: palette.textPrimary,
    fontSize: 16,
    fontWeight: "600",
  },
  description: {
    color: palette.textSecondary,
    fontSize: 13,
    lineHeight: 18,
  },
});
