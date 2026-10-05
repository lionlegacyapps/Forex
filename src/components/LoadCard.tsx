import { Pressable, StyleSheet, Text, View } from "react-native";

import { AppCard } from "@/components/AppCard";
import { StatusBadge } from "@/components/StatusBadge";
import { palette } from "@/constants/theme";
import type { LoadRecord } from "@/types/domain";

type LoadCardProps = {
  load: LoadRecord;
  onPress?: () => void;
};

export const LoadCard = ({ load, onPress }: LoadCardProps) => {
  const content = (
    <AppCard>
      <View style={styles.row}>
        <Text style={styles.loadNumber}>{load.load_number}</Text>
        <StatusBadge status={load.status} />
      </View>
      <Text style={styles.route}>
        {load.origin} → {load.destination}
      </Text>
      <Text style={styles.meta}>Broker: {load.broker_name ?? "Unknown"}</Text>
    </AppCard>
  );

  if (!onPress) return content;

  return (
    <Pressable onPress={onPress} style={styles.pressable}>
      {content}
    </Pressable>
  );
};

const styles = StyleSheet.create({
  pressable: {
    borderRadius: 14,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  loadNumber: {
    color: palette.textPrimary,
    fontSize: 16,
    fontWeight: "700",
  },
  route: {
    color: palette.textPrimary,
    fontSize: 15,
    fontWeight: "500",
  },
  meta: {
    color: palette.textSecondary,
    fontSize: 13,
  },
});
