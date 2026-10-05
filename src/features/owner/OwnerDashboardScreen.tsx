import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const OwnerDashboardScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads, loading, refresh } = useLoads(profile);

  const metrics = useMemo(() => {
    const trucksActive = new Set(
      loads.filter((load) => load.truck_id && load.status !== "canceled").map((load) => load.truck_id),
    ).size;
    const delivered = loads.filter((load) => load.status === "delivered").length;
    const urgent = loads.filter((load) => ["late", "warning", "canceled"].includes(load.status)).length;
    return { trucksActive, delivered, urgent };
  }, [loads]);

  return (
    <ThemedScreen
      title="Owner Dashboard"
      subtitle="Fleet load visibility, alerts, chat, and factoring documents"
      loading={loading}
    >
      <AppCard title="Company Snapshot">
        <View style={styles.metrics}>
          <View style={styles.metricCard}>
            <Text style={styles.value}>{metrics.trucksActive}</Text>
            <Text style={styles.label}>Trucks Active</Text>
          </View>
          <View style={styles.metricCard}>
            <Text style={[styles.value, { color: palette.green }]}>{metrics.delivered}</Text>
            <Text style={styles.label}>Delivered</Text>
          </View>
          <View style={styles.metricCard}>
            <Text style={[styles.value, { color: palette.red }]}>{metrics.urgent}</Text>
            <Text style={styles.label}>Urgent</Text>
          </View>
        </View>
      </AppCard>

      <AppCard title="Navigation">
        <PrimaryButton
          label="Trucks Dashboard"
          onPress={() => router.push("/(app)/(owner)/trucks-dashboard")}
        />
        <PrimaryButton
          label="Loads Overview"
          onPress={() => router.push("/(app)/(owner)/loads-overview")}
          tone="secondary"
        />
        <PrimaryButton
          label="Documents for Factoring"
          onPress={() => router.push("/(app)/(owner)/documents-factoring")}
          tone="secondary"
        />
        {profile?.isOwnerOperator ? (
          <PrimaryButton
            label="Open Driver View"
            onPress={() => router.push("/(app)/(owner)/driver-view")}
            tone="secondary"
          />
        ) : null}
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
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surfaceElevated,
    padding: 12,
  },
  value: {
    color: palette.blue,
    fontWeight: "700",
    fontSize: 22,
  },
  label: {
    color: palette.textSecondary,
    fontSize: 12,
    marginTop: 4,
  },
});
