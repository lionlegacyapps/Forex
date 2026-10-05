import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AppCard } from "@/components/AppCard";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { listAlerts, subscribeToAlerts } from "@/services/notificationService";
import type { AlertRecord } from "@/types/domain";
import { formatDateTime } from "@/utils/format";

type NotificationsCenterScreenProps = {
  title?: string;
};

export const NotificationsCenterScreen = ({
  title = "Notifications",
}: NotificationsCenterScreenProps) => {
  const { profile } = useAuth();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);

  useEffect(() => {
    if (!profile) return;
    let mounted = true;
    const initialize = async () => {
      const initial = await listAlerts(profile);
      if (mounted) setAlerts(initial);
    };
    initialize();

    const channel = subscribeToAlerts(profile, (alert) => {
      setAlerts((current) => [alert, ...current]);
    });

    return () => {
      mounted = false;
      channel.unsubscribe();
    };
  }, [profile]);

  return (
    <ThemedScreen
      title={title}
      subtitle="Push and in-app events for loads, statuses, documents, and chat"
    >
      {alerts.length === 0 ? (
        <AppCard title="No alerts yet">
          <Text style={styles.secondary}>
            Incoming updates will appear here as your company activity changes.
          </Text>
        </AppCard>
      ) : (
        alerts.map((alert) => (
          <AppCard key={alert.id}>
            <View style={styles.row}>
              <Text style={styles.alertTitle}>{alert.title}</Text>
              <Text style={styles.event}>{alert.event_type}</Text>
            </View>
            <Text style={styles.body}>{alert.message}</Text>
            <Text style={styles.meta}>{formatDateTime(alert.created_at)}</Text>
          </AppCard>
        ))
      )}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },
  alertTitle: {
    color: palette.textPrimary,
    fontWeight: "700",
    fontSize: 15,
    flex: 1,
  },
  event: {
    color: palette.blue,
    fontSize: 12,
    textTransform: "uppercase",
  },
  body: {
    color: palette.textSecondary,
    fontSize: 14,
    lineHeight: 20,
  },
  meta: {
    color: palette.textSecondary,
    fontSize: 12,
  },
  secondary: {
    color: palette.textSecondary,
  },
});
