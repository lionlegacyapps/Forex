import { useState } from "react";
import { StyleSheet, Text } from "react-native";

import { AppCard } from "@/components/AppCard";
import { InputField } from "@/components/InputField";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { sendDocumentToBrokerEmail } from "@/services/brokerDocumentsService";

export const OwnerDocumentsFactoringScreen = () => {
  const { profile } = useAuth();
  const [loadId, setLoadId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [factoringEmail, setFactoringEmail] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!profile || !loadId || !documentId || !factoringEmail) return;
    setSending(true);
    try {
      await sendDocumentToBrokerEmail({
        companyId: profile.companyId,
        loadId,
        brokerEmail: factoringEmail,
        documentId,
        requestedBy: profile.id,
      });
      setStatus("Document submission request sent.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to send.");
    } finally {
      setSending(false);
    }
  };

  return (
    <ThemedScreen
      title="Documents for Factoring"
      subtitle="Prepare and send load paperwork to factoring companies"
    >
      <AppCard
        title="Factoring Submission"
        description="Uses a placeholder server hook; connect to your production factoring/email workflow."
      >
        <InputField
          label="Load ID"
          value={loadId}
          onChangeText={setLoadId}
          autoCapitalize="none"
          placeholder="load-uuid"
        />
        <InputField
          label="Document ID"
          value={documentId}
          onChangeText={setDocumentId}
          autoCapitalize="none"
          placeholder="document-uuid"
        />
        <InputField
          label="Factoring Email"
          value={factoringEmail}
          onChangeText={setFactoringEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="funding@factoring.com"
        />
        <PrimaryButton
          label="Send Document Package"
          onPress={handleSend}
          loading={sending}
          disabled={!loadId || !documentId || !factoringEmail}
        />
        {status ? <Text style={styles.status}>{status}</Text> : null}
      </AppCard>
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  status: {
    color: palette.textSecondary,
    fontSize: 13,
  },
});
