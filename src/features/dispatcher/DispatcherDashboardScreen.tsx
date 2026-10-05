import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const DispatcherDashboardScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads, loading, refresh } = useLoads(profile);

  const metrics = useMemo(() => {
    const inTransit = loads.filter((load) => ["in_transit", "arrived", "loaded"].includes(load.status)).length;
    const delivered = loads.filter((load) => load.status === "delivered").length;
    const issues = loads.filter((load) => ["warning", "late", "canceled"].includes(load.status)).length;
    return { inTransit, delivered, issues };
  }, [loads]);

  return (
    <ThemedScreen
      title="Dispatcher Dashboard"
      subtitle="Drivers status, communications hub, broker panel, and recommended loads"
      loading={loading}
    >
      <AppCard title="Operations Snapshot">
        <View style={styles.metrics}>
          <View style={styles.metricCard}>
            <Text style={styles.metricValue}>{metrics.inTransit}</Text>
            <Text style={styles.metricLabel}>Active Loads</Text>
          </View>
          <View style={styles.metricCard}>
            <Text style={[styles.metricValue, { color: palette.green }]}>{metrics.delivered}</Text>
            <Text style={styles.metricLabel}>Delivered</Text>
          </View>
          <View style={styles.metricCard}>
            <Text style={[styles.metricValue, { color: palette.red }]}>{metrics.issues}</Text>
            <Text style={styles.metricLabel}>Alerts</Text>
          </View>
        </View>
      </AppCard>

      <AppCard title="Quick Actions">
        <PrimaryButton
          label="Drivers Status on Loads"
          onPress={() => router.push("/(app)/(dispatcher)/drivers-status")}
        />
        <PrimaryButton
          label="Communications Hub"
          onPress={() => router.push("/(app)/(dispatcher)/communications-hub")}
          tone="secondary"
        />
        <PrimaryButton
          label="Broker Call / Text Panel"
          onPress={() => router.push("/(app)/(dispatcher)/broker-panel")}
          tone="secondary"
        />
        <PrimaryButton
          label="Recommended Loads"
          onPress={() => router.push("/(app)/(dispatcher)/recommended-loads")}
          tone="secondary"
        />
        <PrimaryButton
          label="Alerts Center"
          onPress={() => router.push("/(app)/(dispatcher)/alerts-center")}
          tone="secondary"
        />
      </AppCard>

      <PrimaryButton label="Refresh Dashboard" onPress={refresh} tone="secondary" />
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  metrics: {
    flexDirection: "row",
    gap: 10,
  },
  metricCard: {
    flex: 1,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 12,
    padding: 12,
    backgroundColor: palette.surfaceElevated,
  },
  metricValue: {
    color: palette.blue,
    fontSize: 22,
    fontWeight: "700",
  },
  metricLabel: {
    color: palette.textSecondary,
    marginTop: 4,
    fontSize: 12,
  },
});
