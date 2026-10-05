import { StyleSheet, Text } from "react-native";
import { useRouter } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";

export const CommunicationsHubScreen = () => {
  const router = useRouter();

  return (
    <ThemedScreen
      title="Communications Hub"
      subtitle="Centralized messaging with drivers, owners, and brokers"
    >
      <AppCard
        title="Team Messaging"
        description="Use shared chat to keep dispatch, owner, and driver aligned."
      >
        <PrimaryButton
          label="Open Shared Chat"
          onPress={() => router.push("/(app)/(dispatcher)/chat")}
        />
      </AppCard>

      <AppCard
        title="Broker Call/Text Panel"
        description="Placeholder panel with future hooks for Twilio, Telnyx, and Vapi."
      >
        <PrimaryButton
          label="Open Broker Panel"
          onPress={() => router.push("/(app)/(dispatcher)/broker-panel")}
          tone="secondary"
        />
      </AppCard>

      <AppCard
        title="One-Button Broker Document Share"
        description="Route factoring documents to broker email when integrations are ready."
      >
        <Text style={styles.secondary}>
          Document email delivery is scaffolded with server-side hook placeholders.
        </Text>
        <PrimaryButton
          label="Open Documents Center"
          onPress={() => router.push("/(app)/(dispatcher)/documents-center")}
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
