import { Link } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { palette } from "@/constants/theme";

export default function NotFoundScreen() {
  return (
    <View style={styles.root}>
      <Text style={styles.title}>Route not found</Text>
      <Text style={styles.subtitle}>The requested mobile screen does not exist.</Text>
      <Link href="/(app)" style={styles.link}>
        Return to app
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: palette.background,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 20,
  },
  title: {
    color: palette.textPrimary,
    fontWeight: "700",
    fontSize: 24,
  },
  subtitle: {
    color: palette.textSecondary,
    textAlign: "center",
  },
  link: {
    color: palette.blue,
    fontWeight: "700",
  },
});
