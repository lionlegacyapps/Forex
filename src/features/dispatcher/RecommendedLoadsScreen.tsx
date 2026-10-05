import { useEffect, useState } from "react";
import { StyleSheet, Text } from "react-native";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { listRecommendedLoads } from "@/services/recommendedLoadsService";
import { formatDateTime } from "@/utils/format";

type RecommendedLoad = {
  id: string;
  load_number: string;
  origin: string;
  destination: string;
  score: number | null;
  reason: string | null;
  status: string | null;
  created_at: string;
  company_id: string;
};

export const RecommendedLoadsScreen = () => {
  const { profile } = useAuth();
  const [loads, setLoads] = useState<RecommendedLoad[]>([]);

  const refresh = async () => {
    if (!profile) return;
    setLoads(await listRecommendedLoads(profile.companyId));
  };

  useEffect(() => {
    if (!profile) return;
    const loadInitialRecommendations = async () => {
      const nextLoads = await listRecommendedLoads(profile.companyId);
      setLoads(nextLoads);
    };
    loadInitialRecommendations();
  }, [profile?.companyId]);

  return (
    <ThemedScreen
      title="Recommended Loads"
      subtitle="Loads pushed from dispatch board after cancellations or better opportunities"
    >
      {loads.length === 0 ? (
        <AppCard title="No recommendations">
          <Text style={styles.secondary}>
            Recommendations populate when canceled loads or better options are available.
          </Text>
        </AppCard>
      ) : (
        loads.map((load) => (
          <AppCard
            key={load.id}
            title={load.load_number}
            description={`${load.origin} → ${load.destination}`}
          >
            <Text style={styles.secondary}>
              Score: {load.score ?? "-"} • Status: {load.status ?? "pending"}
            </Text>
            <Text style={styles.secondary}>Reason: {load.reason ?? "-"}</Text>
            <Text style={styles.secondary}>Created: {formatDateTime(load.created_at)}</Text>
          </AppCard>
        ))
      )}
      <PrimaryButton label="Refresh Recommendations" onPress={refresh} tone="secondary" />
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
    fontSize: 13,
  },
});
