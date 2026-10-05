import { StyleSheet, Text, View } from "react-native";

import { getStatusStyle } from "@/constants/status";
import type { LoadStatus } from "@/types/domain";

export const StatusBadge = ({ status }: { status: LoadStatus }) => {
  const badge = getStatusStyle(status);
  return (
    <View style={[styles.badge, { borderColor: badge.color }]}>
      <Text style={[styles.text, { color: badge.color }]}>{badge.label}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  text: {
    fontSize: 12,
    fontWeight: "700",
  },
});
