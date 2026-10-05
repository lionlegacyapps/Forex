import { useRouter } from "expo-router";

import { LoadCard } from "@/components/LoadCard";
import { ThemedScreen } from "@/components/ThemedScreen";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";

export const OwnerLoadsOverviewScreen = () => {
  const router = useRouter();
  const { profile } = useAuth();
  const { loads, loading } = useLoads(profile);

  return (
    <ThemedScreen title="Loads Overview" subtitle="Company-wide load visibility" loading={loading}>
      {loads.map((load) => (
        <LoadCard
          key={load.id}
          load={load}
          onPress={() => router.push(`/(app)/(owner)/driver-load-details/${load.id}`)}
        />
      ))}
    </ThemedScreen>
  );
};
