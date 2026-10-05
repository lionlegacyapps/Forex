import { useState } from "react";
import { StyleSheet, Text } from "react-native";

import { AppCard } from "@/components/AppCard";
import { InputField } from "@/components/InputField";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { telephonyHooks } from "@/services/telephonyHooks";

export const BrokerPanelScreen = () => {
  const [brokerPhone, setBrokerPhone] = useState("");
  const [loadId, setLoadId] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const handleCall = async () => {
    try {
      await telephonyHooks.callBroker("twilio", { loadId, brokerPhone });
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Call hook failed.");
    }
  };

  const handleText = async () => {
    try {
      await telephonyHooks.textBroker("telnyx", {
        loadId,
        brokerPhone,
        note: "Dispatch update",
      });
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Text hook failed.");
    }
  };

  return (
    <ThemedScreen
      title="Broker Call / Text Panel"
      subtitle="Telephony integration placeholder hooks for Twilio/Telnyx/Vapi"
    >
      <AppCard
        title="Outbound Broker Contact"
        description="UI scaffolded now, service hooks ready for future backend integration."
      >
        <InputField
          label="Load ID"
          value={loadId}
          onChangeText={setLoadId}
          autoCapitalize="none"
          placeholder="load-uuid"
        />
        <InputField
          label="Broker Phone"
          value={brokerPhone}
          onChangeText={setBrokerPhone}
          keyboardType="phone-pad"
          placeholder="+1..."
        />
        <PrimaryButton label="Call Broker (Twilio Hook)" onPress={handleCall} />
        <PrimaryButton
          label="Text Broker (Telnyx Hook)"
          onPress={handleText}
          tone="secondary"
        />
        {status ? <Text style={styles.status}>{status}</Text> : null}
      </AppCard>
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  status: {
    color: palette.textSecondary,
    fontSize: 12,
  },
});
