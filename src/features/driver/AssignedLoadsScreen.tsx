import { useRouter } from "expo-router";
import { Text } from "react-native";

import { AppCard } from "@/components/AppCard";
import { LoadCard } from "@/components/LoadCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const AssignedLoadsScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads, loading, refresh } = useLoads(profile, true);

  return (
    <ThemedScreen title="Assigned Loads" subtitle="Only loads assigned to your driver profile" loading={loading}>
      {loads.length === 0 ? (
        <AppCard title="No assigned loads">
          <Text style={{ color: palette.textSecondary }}>
            New assignments will appear here and trigger push notifications.
          </Text>
        </AppCard>
      ) : (
        loads.map((load) => (
          <LoadCard
            key={load.id}
            load={load}
            onPress={() => router.push(`/(app)/(driver)/loads/${load.id}`)}
          />
        ))
      )}
      <PrimaryButton label="Refresh Loads" onPress={refresh} tone="secondary" />
    </ThemedScreen>
  );
};
