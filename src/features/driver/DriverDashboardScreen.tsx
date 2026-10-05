import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const DriverDashboardScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads, loading, refresh } = useLoads(profile, true);

  const stats = useMemo(() => {
    const active = loads.filter((load) => ["assigned", "in_transit", "arrived", "loaded"].includes(load.status))
      .length;
    const delivered = loads.filter((load) => load.status === "delivered").length;
    const urgent = loads.filter((load) => ["warning", "late", "canceled"].includes(load.status)).length;
    return { active, delivered, urgent };
  }, [loads]);

  return (
    <ThemedScreen
      title="Driver Dashboard"
      subtitle="Assigned loads, status updates, location check-ins, and POD uploads"
      loading={loading}
    >
      <AppCard title="Today">
        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Text style={styles.statNumber}>{stats.active}</Text>
            <Text style={styles.statLabel}>Active Loads</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={[styles.statNumber, { color: palette.green }]}>{stats.delivered}</Text>
            <Text style={styles.statLabel}>Delivered</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={[styles.statNumber, { color: palette.red }]}>{stats.urgent}</Text>
            <Text style={styles.statLabel}>Urgent</Text>
          </View>
        </View>
      </AppCard>

      <AppCard title="Actions" description="Update statuses and upload paperwork in real time.">
        <PrimaryButton label="Open Assigned Loads" onPress={() => router.push("/(app)/(driver)/loads")} />
        <PrimaryButton
          label="Update Status (Arrived / Loaded / Delivered / Empty)"
          onPress={() => router.push("/(app)/(driver)/status-updates")}
          tone="secondary"
        />
        <PrimaryButton
          label="GPS Check-In"
          onPress={() => router.push("/(app)/(driver)/location-checkin")}
          tone="secondary"
        />
        <PrimaryButton
          label="Upload POD / Paperwork"
          onPress={() => router.push("/(app)/(driver)/documents")}
          tone="secondary"
        />
      </AppCard>

      <PrimaryButton label="Refresh Dashboard" onPress={refresh} tone="secondary" />
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  statsRow: {
    flexDirection: "row",
    gap: 10,
  },
  statCard: {
    flex: 1,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surfaceElevated,
    padding: 12,
    gap: 4,
  },
  statNumber: {
    color: palette.blue,
    fontSize: 24,
    fontWeight: "700",
  },
  statLabel: {
    color: palette.textSecondary,
    fontSize: 12,
  },
});
