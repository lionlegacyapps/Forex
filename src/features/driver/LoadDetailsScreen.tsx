import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { StatusBadge } from "@/components/StatusBadge";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { getLoadById } from "@/services/loadService";
import type { LoadRecord } from "@/types/domain";
import { formatDateTime } from "@/utils/format";

type LoadDetailsScreenProps = {
  loadId: string;
  routeMode?: "driver" | "ownerDriver";
};

export const LoadDetailsScreen = ({
  loadId,
  routeMode = "driver",
}: LoadDetailsScreenProps) => {
  const router = useRouter();
  const [load, setLoad] = useState<LoadRecord | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDetails = async () => {
      setLoading(true);
      setLoad(await getLoadById(loadId));
      setLoading(false);
    };
    loadDetails();
  }, [loadId]);

  const routeMap =
    routeMode === "ownerDriver"
      ? {
          status: "/(app)/(owner)/driver-status-updates",
          documents: "/(app)/(owner)/driver-documents",
          location: "/(app)/(owner)/driver-location-checkin",
        }
      : {
          status: "/(app)/(driver)/status-updates",
          documents: "/(app)/(driver)/documents",
          location: "/(app)/(driver)/location-checkin",
        };

  return (
    <ThemedScreen title="Load Details" subtitle="Trip details, documents, and status flow" loading={loading}>
      {!load ? (
        <AppCard title="Load unavailable">
          <Text style={styles.secondary}>This load was not found or is outside your access scope.</Text>
        </AppCard>
      ) : (
        <>
          <AppCard title={load.load_number}>
            <StatusBadge status={load.status} />
            <Text style={styles.route}>
              {load.origin} → {load.destination}
            </Text>
            <View style={styles.row}>
              <Text style={styles.label}>Pickup</Text>
              <Text style={styles.value}>{formatDateTime(load.pickup_at)}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Delivery</Text>
              <Text style={styles.value}>{formatDateTime(load.delivery_at)}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Broker</Text>
              <Text style={styles.value}>{load.broker_name ?? "-"}</Text>
            </View>
          </AppCard>

          <AppCard title="Driver Actions">
            <PrimaryButton
              label="Update Status"
              onPress={() => router.push(`${routeMap.status}?loadId=${load.id}`)}
            />
            <PrimaryButton
              label="Upload POD / Paperwork"
              onPress={() => router.push(`${routeMap.documents}?loadId=${load.id}`)}
              tone="secondary"
            />
            <PrimaryButton
              label="GPS Check-In"
              onPress={() => router.push(`${routeMap.location}?loadId=${load.id}`)}
              tone="secondary"
            />
          </AppCard>
        </>
      )}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 8,
  },
  label: {
    color: palette.textSecondary,
  },
  value: {
    color: palette.textPrimary,
    fontWeight: "600",
  },
  route: {
    color: palette.textPrimary,
    fontSize: 15,
    fontWeight: "600",
  },
  secondary: {
    color: palette.textSecondary,
  },
});
