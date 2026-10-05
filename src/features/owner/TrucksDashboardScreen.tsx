import { useMemo } from "react";
import { StyleSheet, Text } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { StatusBadge } from "@/components/StatusBadge";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const TrucksDashboardScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads } = useLoads(profile);

  const truckLoads = useMemo(() => {
    const grouped = new Map<string, typeof loads>();
    loads.forEach((load) => {
      const truckId = load.truck_id ?? "unassigned";
      if (!grouped.has(truckId)) grouped.set(truckId, []);
      grouped.get(truckId)?.push(load);
    });
    return grouped;
  }, [loads]);

  return (
    <ThemedScreen title="Trucks Dashboard" subtitle="Truck-level load and status visibility">
      {Array.from(truckLoads.entries()).map(([truckId, truckLoadSet]) => {
        const currentLoad = truckLoadSet[0];
        return (
          <AppCard
            key={truckId}
            title={truckId === "unassigned" ? "Unassigned Truck" : `Truck ${truckId}`}
          >
            {currentLoad ? <StatusBadge status={currentLoad.status} /> : null}
            <Text style={styles.secondary}>Active loads: {truckLoadSet.length}</Text>
            <PrimaryButton
              label="View Truck Status"
              tone="secondary"
              onPress={() => router.push(`/(app)/(owner)/truck-status?truckId=${truckId}`)}
            />
          </AppCard>
        );
      })}
      {truckLoads.size === 0 ? (
        <AppCard title="No trucks active">
          <Text style={styles.secondary}>No truck-linked loads are currently active.</Text>
        </AppCard>
      ) : null}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
  },
});
