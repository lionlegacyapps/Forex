import { useEffect, useMemo, useState } from "react";
import { Linking, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useLoads } from "@/hooks/useLoads";
import {
  getDocumentDownloadUrl,
  listLoadDocuments,
  uploadLoadDocumentFromDevice,
} from "@/services/documentService";
import { emitNotificationEvent } from "@/services/notificationService";
import { formatDateTime } from "@/utils/format";

const documentTypes = ["pod", "bol", "lumper_receipt", "scale_ticket", "other"] as const;

type LoadDocument = {
  id: string;
  file_name: string;
  document_type: string;
  file_path: string;
  created_at: string;
};

type DriverDocumentsScreenProps = {
  title?: string;
};

export const DriverDocumentsScreen = ({
  title = "Upload POD / Paperwork",
}: DriverDocumentsScreenProps) => {
  const params = useLocalSearchParams<{ loadId?: string }>();
  const targetLoadId = params.loadId;
  const { profile } = useAuth();
  const { loads } = useLoads(profile, true);
  const [selectedType, setSelectedType] = useState<(typeof documentTypes)[number]>("pod");
  const [uploading, setUploading] = useState(false);
  const [documents, setDocuments] = useState<LoadDocument[]>([]);

  const selectedLoad = useMemo(
    () => loads.find((load) => load.id === targetLoadId) ?? loads[0] ?? null,
    [loads, targetLoadId],
  );

  const refreshDocuments = async () => {
    if (!profile || !selectedLoad) return;
    setDocuments(
      await listLoadDocuments({ companyId: profile.companyId, loadId: selectedLoad.id }),
    );
  };

  useEffect(() => {
    if (!profile || !selectedLoad) return;
    const loadDocuments = async () => {
      const nextDocuments = await listLoadDocuments({
        companyId: profile.companyId,
        loadId: selectedLoad.id,
      });
      setDocuments(nextDocuments);
    };
    loadDocuments();
  }, [selectedLoad?.id, profile?.companyId]);

  const handleUpload = async () => {
    if (!profile || !selectedLoad) return;
    setUploading(true);

    const uploadedPath = await uploadLoadDocumentFromDevice({
      loadId: selectedLoad.id,
      companyId: profile.companyId,
      userId: profile.id,
      documentType: selectedType,
    });

    if (uploadedPath) {
      await emitNotificationEvent({
        companyId: profile.companyId,
        actorId: profile.id,
        eventType: "document_uploaded",
        title: "Document Uploaded",
        message: `${profile.fullName} uploaded ${selectedType} for ${selectedLoad.load_number}.`,
        loadId: selectedLoad.id,
      });
      await refreshDocuments();
    }

    setUploading(false);
  };

  return (
    <ThemedScreen title={title} subtitle="POD, BOL, lumper receipts, and scale tickets">
      {!selectedLoad ? (
        <AppCard title="No load selected">
          <Text style={styles.secondary}>Assign a load first to upload paperwork.</Text>
        </AppCard>
      ) : (
        <>
          <AppCard
            title={selectedLoad.load_number}
            description={`${selectedLoad.origin} → ${selectedLoad.destination}`}
          >
            <View style={styles.typeRow}>
              {documentTypes.map((type) => (
                <PrimaryButton
                  key={type}
                  label={type.replace("_", " ").toUpperCase()}
                  onPress={() => setSelectedType(type)}
                  tone={selectedType === type ? "primary" : "secondary"}
                />
              ))}
            </View>
            <PrimaryButton
              label={`Upload ${selectedType.replace("_", " ").toUpperCase()}`}
              onPress={handleUpload}
              loading={uploading}
            />
          </AppCard>

          <AppCard title="Existing Documents">
            {documents.length === 0 ? (
              <Text style={styles.secondary}>No documents uploaded yet for this load.</Text>
            ) : (
              documents.map((doc) => (
                <View key={doc.id} style={styles.documentRow}>
                  <View style={styles.documentInfo}>
                    <Text style={styles.documentName}>{doc.file_name}</Text>
                    <Text style={styles.secondary}>
                      {doc.document_type} • {formatDateTime(doc.created_at)}
                    </Text>
                  </View>
                  <PrimaryButton
                    label="Open"
                    tone="secondary"
                    onPress={async () => {
                      const url = await getDocumentDownloadUrl(doc.file_path);
                      if (url) await Linking.openURL(url);
                    }}
                  />
                </View>
              ))
            )}
          </AppCard>
        </>
      )}
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondary: {
    color: palette.textSecondary,
  },
  typeRow: {
    gap: 8,
  },
  documentRow: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 10,
    gap: 8,
    backgroundColor: palette.surfaceElevated,
  },
  documentInfo: {
    gap: 4,
  },
  documentName: {
    color: palette.textPrimary,
    fontWeight: "600",
  },
});
