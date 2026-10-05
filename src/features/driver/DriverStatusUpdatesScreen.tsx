import { useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { loadStatusUpdateOptions } from "@/constants/status";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";
import { emitNotificationEvent } from "@/services/notificationService";
import { updateLoadStatus } from "@/services/loadService";
import type { LoadStatus } from "@/types/domain";

type StatusEventMap = Record<
  LoadStatus,
  {
    eventType:
      | "load_status_changed"
      | "driver_arrived"
      | "driver_loaded"
      | "driver_delivered"
      | "driver_empty";
    title: string;
  }
>;

const statusEventMap: Partial<StatusEventMap> = {
  arrived: { eventType: "driver_arrived", title: "Driver Arrived" },
  loaded: { eventType: "driver_loaded", title: "Driver Loaded" },
  delivered: { eventType: "driver_delivered", title: "Driver Delivered" },
  empty: { eventType: "driver_empty", title: "Driver Empty" },
};

export const DriverStatusUpdatesScreen = () => {
  const params = useLocalSearchParams<{ loadId?: string }>();
  const targetLoadId = params.loadId;
  const { profile } = useAuth();
  const { loads, loading, refresh } = useLoads(profile, true);
  const [savingStatus, setSavingStatus] = useState<LoadStatus | null>(null);

  const selectedLoad = useMemo(
    () => loads.find((load) => load.id === targetLoadId) ?? loads[0] ?? null,
    [loads, targetLoadId],
  );

  const handleStatusChange = async (status: LoadStatus) => {
    if (!profile || !selectedLoad) return;
    setSavingStatus(status);

    await updateLoadStatus({
      loadId: selectedLoad.id,
      status,
      updatedBy: profile.id,
      companyId: profile.companyId,
    });

    const statusEvent = statusEventMap[status];
    await emitNotificationEvent({
      companyId: profile.companyId,
      actorId: profile.id,
      eventType: statusEvent?.eventType ?? "load_status_changed",
      title: statusEvent?.title ?? "Load Status Changed",
      message: `${selectedLoad.load_number} status is now ${status.replace("_", " ")}.`,
      loadId: selectedLoad.id,
    });

    await refresh();
    setSavingStatus(null);
  };

  return (
    <ThemedScreen
      title="Status Updates"
      subtitle="Mark Arrived, Loaded, Delivered, or Empty and notify dispatch + owner"
      loading={loading}
    >
      {!selectedLoad ? (
        <AppCard title="No active load">
          <Text style={styles.secondary}>Assign at least one load to update statuses.</Text>
        </AppCard>
      ) : (
        <AppCard title={selectedLoad.load_number}>
          <Text style={styles.route}>
            {selectedLoad.origin} → {selectedLoad.destination}
          </Text>
          <View style={styles.actions}>
            {loadStatusUpdateOptions.map((option) => (
              <PrimaryButton
                key={option.status}
                label={option.label}
                onPress={() => handleStatusChange(option.status)}
                loading={savingStatus === option.status}
                tone={option.status === "delivered" || option.status === "empty" ? "primary" : "secondary"}
              />
            ))}
          </View>
        </AppCard>
      )}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  route: {
    color: palette.textPrimary,
    fontWeight: "600",
  },
  secondary: {
    color: palette.textSecondary,
  },
  actions: {
    gap: 8,
  },
});
