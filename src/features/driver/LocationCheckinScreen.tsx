import { useMemo, useState } from "react";
import { StyleSheet, Text } from "react-native";
import { useLocalSearchParams } from "expo-router";
import * as Location from "expo-location";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";
import { sendLocationCheckin } from "@/services/loadService";

type LocationCheckinScreenProps = {
  asOwnerDriver?: boolean;
};

export const LocationCheckinScreen = ({ asOwnerDriver }: LocationCheckinScreenProps) => {
  const params = useLocalSearchParams<{ loadId?: string }>();
  const targetLoadId = params.loadId;
  const { profile } = useAuth();
  const { loads } = useLoads(profile, true);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const selectedLoad = useMemo(
    () => loads.find((load) => load.id === targetLoadId) ?? loads[0] ?? null,
    [loads, targetLoadId],
  );

  const handleCheckIn = async () => {
    if (!profile || !selectedLoad) return;
    setSubmitting(true);
    setMessage(null);

    const permission = await Location.requestForegroundPermissionsAsync();
    if (permission.status !== "granted") {
      setMessage("Location permission is required for GPS check-in.");
      setSubmitting(false);
      return;
    }

    const location = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });

    await sendLocationCheckin({
      loadId: selectedLoad.id,
      companyId: profile.companyId,
      userId: profile.id,
      latitude: location.coords.latitude,
      longitude: location.coords.longitude,
    });

    setMessage("Location check-in sent successfully.");
    setSubmitting(false);
  };

  return (
    <ThemedScreen
      title={asOwnerDriver ? "Driver GPS Check-In" : "GPS / Location Check-In"}
      subtitle="Share current location for your assigned load"
    >
      {!selectedLoad ? (
        <AppCard title="No load selected">
          <Text style={styles.secondary}>Assign a load first to submit location check-ins.</Text>
        </AppCard>
      ) : (
        <AppCard
          title={selectedLoad.load_number}
          description={`${selectedLoad.origin} → ${selectedLoad.destination}`}
        >
          <PrimaryButton label="Send Current Location" onPress={handleCheckIn} loading={submitting} />
          {message ? <Text style={styles.message}>{message}</Text> : null}
        </AppCard>
      )}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
  },
  message: {
    color: palette.textSecondary,
    fontSize: 13,
  },
});
