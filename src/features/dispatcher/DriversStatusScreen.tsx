import { StyleSheet, Text, View } from "react-native";

import { AppCard } from "@/components/AppCard";
import { LoadCard } from "@/components/LoadCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const DriversStatusScreen = () => {
  const { profile } = useAuth();
  const { loads, loading, refresh } = useLoads(profile);

  return (
    <ThemedScreen
      title="Drivers Status on Loads"
      subtitle="Real-time lane visibility for dispatcher-assigned drivers"
      loading={loading}
    >
      {loads.length === 0 ? (
        <AppCard title="No assigned activity">
          <Text style={styles.secondary}>No loads are currently assigned to your dispatch profile.</Text>
        </AppCard>
      ) : (
        loads.map((load) => (
          <View key={load.id} style={styles.wrap}>
            <LoadCard load={load} />
          </View>
        ))
      )}
      <PrimaryButton label="Refresh Status" onPress={refresh} tone="secondary" />
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
  },
  wrap: {
    gap: 8,
  },
});
