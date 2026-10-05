import { StyleSheet, Text } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";

export const OwnerDriverViewScreen = () => {
  const router = useRouter();
  return (
    <ThemedScreen
      title="Driver View"
      subtitle="Owner-operator access to driver workflows and navigation"
    >
      <AppCard
        title="Owner-Operator Mode"
        description="You can use driver-specific features while retaining owner visibility."
      >
        <Text style={styles.secondary}>
          Assigned loads, status changes, GPS check-ins, and POD uploads are available below.
        </Text>
        <PrimaryButton
          label="Driver Assigned Loads"
          onPress={() => router.push("/(app)/(owner)/driver-loads")}
        />
        <PrimaryButton
          label="Driver Status Updates"
          onPress={() => router.push("/(app)/(owner)/driver-status-updates")}
          tone="secondary"
        />
        <PrimaryButton
          label="Driver GPS Check-In"
          onPress={() => router.push("/(app)/(owner)/driver-location-checkin")}
          tone="secondary"
        />
        <PrimaryButton
          label="Driver Document Upload"
          onPress={() => router.push("/(app)/(owner)/driver-documents")}
          tone="secondary"
        />
      </AppCard>
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
    fontSize: 13,
  },
});
