import { useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AppCard } from "@/components/AppCard";
import { InputField } from "@/components/InputField";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";
import { listLoadDocuments } from "@/services/documentService";
import { sendDocumentToBrokerEmail } from "@/services/brokerDocumentsService";
import { formatDateTime } from "@/utils/format";

export const DispatcherDocumentsCenterScreen = () => {
  const { profile } = useAuth();
  const { loads } = useLoads(profile);
  const [brokerEmail, setBrokerEmail] = useState("");
  const [selectedLoadId, setSelectedLoadId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<
    Array<{
      id: string;
      file_name: string;
      document_type: string;
      file_path: string;
      created_at: string;
    }>
  >([]);

  const selectedLoad = useMemo(
    () => loads.find((load) => load.id === selectedLoadId) ?? loads[0] ?? null,
    [loads, selectedLoadId],
  );

  useEffect(() => {
    if (!selectedLoad || !profile) return;
    const loadDocs = async () => {
      setDocuments(
        await listLoadDocuments({
          loadId: selectedLoad.id,
          companyId: profile.companyId,
        }),
      );
    };
    loadDocs();
  }, [selectedLoad?.id, profile?.companyId]);

  const handleSendToBroker = async (documentId: string) => {
    if (!profile || !selectedLoad || !brokerEmail) return;
    setSendingId(documentId);
    try {
      await sendDocumentToBrokerEmail({
        companyId: profile.companyId,
        loadId: selectedLoad.id,
        brokerEmail,
        documentId,
        requestedBy: profile.id,
      });
      setStatus("Document sent to broker email.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to send document.");
    } finally {
      setSendingId(null);
    }
  };

  return (
    <ThemedScreen
      title="Documents Center"
      subtitle="Review load documents and send to broker email in one action"
    >
      <AppCard title="Select Load">
        {loads.map((load) => (
          <PrimaryButton
            key={load.id}
            label={`${load.load_number}: ${load.origin} → ${load.destination}`}
            onPress={() => setSelectedLoadId(load.id)}
            tone={selectedLoad?.id === load.id ? "primary" : "secondary"}
          />
        ))}
      </AppCard>

      <AppCard
        title="Broker Email"
        description="This button currently calls a placeholder Edge Function hook."
      >
        <InputField
          label="Broker Email"
          value={brokerEmail}
          onChangeText={setBrokerEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="broker@domain.com"
        />
      </AppCard>

      <AppCard title="Load Documents">
        {documents.length === 0 ? (
          <Text style={styles.secondary}>No documents available for the selected load.</Text>
        ) : (
          documents.map((doc) => (
            <View key={doc.id} style={styles.docRow}>
              <View style={styles.info}>
                <Text style={styles.name}>{doc.file_name}</Text>
                <Text style={styles.secondary}>
                  {doc.document_type} • {formatDateTime(doc.created_at)}
                </Text>
              </View>
              <PrimaryButton
                label="Send to Broker"
                onPress={() => handleSendToBroker(doc.id)}
                loading={sendingId === doc.id}
                disabled={!brokerEmail || !selectedLoad}
              />
            </View>
          ))
        )}
        {status ? <Text style={styles.secondary}>{status}</Text> : null}
      </AppCard>
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  docRow: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surfaceElevated,
    padding: 10,
    gap: 10,
  },
  info: {
    gap: 4,
  },
  name: {
    color: palette.textPrimary,
    fontWeight: "600",
  },
  secondary: {
    color: palette.textSecondary,
    fontSize: 12,
  },
});
