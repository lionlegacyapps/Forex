import { useRouter } from "expo-router";
import { Text } from "react-native";

import { AppCard } from "@/components/AppCard";
import { LoadCard } from "@/components/LoadCard";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const OwnerDriverLoadsScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads, loading } = useLoads(profile, true);

  return (
    <ThemedScreen title="Driver Assigned Loads" subtitle="Owner-operator driver load assignments" loading={loading}>
      {loads.length === 0 ? (
        <AppCard title="No driver loads">
          <Text style={{ color: palette.textSecondary }}>
            No driver-assigned loads available for this account.
          </Text>
        </AppCard>
      ) : (
        loads.map((load) => (
          <LoadCard
            key={load.id}
            load={load}
            onPress={() => router.push(`/(app)/(owner)/driver-load-details/${load.id}`)}
          />
        ))
      )}
    </ThemedScreen>
  );
};
