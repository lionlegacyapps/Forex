import { useMemo } from "react";
import { StyleSheet, Text } from "react-native";
import { useLocalSearchParams } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { LoadCard } from "@/components/LoadCard";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const TruckStatusScreen = () => {
  const params = useLocalSearchParams<{ truckId?: string }>();
  const truckId = params.truckId ?? "";
  const { profile } = useAuth();
  const { loads } = useLoads(profile);

  const filtered = useMemo(
    () => loads.filter((load) => (truckId === "unassigned" ? !load.truck_id : load.truck_id === truckId)),
    [loads, truckId],
  );

  return (
    <ThemedScreen
      title="Truck Status"
      subtitle={truckId ? `Current load statuses for truck ${truckId}` : "Truck load statuses"}
    >
      {filtered.length === 0 ? (
        <AppCard title="No matching loads">
          <Text style={styles.secondary}>No loads found for this truck at the moment.</Text>
        </AppCard>
      ) : (
        filtered.map((load) => <LoadCard key={load.id} load={load} />)
      )}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
  },
});
