import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { palette } from "@/constants/theme";

export const AppLoadingScreen = ({ message }: { message: string }) => (
  <View style={styles.root}>
    <ActivityIndicator size="large" color={palette.blue} />
    <Text style={styles.text}>{message}</Text>
  </View>
);

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: palette.background,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    padding: 20,
  },
  text: {
    color: palette.textSecondary,
    textAlign: "center",
  },
});
