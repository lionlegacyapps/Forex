import { useEffect, useMemo, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { listMessages, listThreads, sendMessage } from "@/services/chatService";
import type { ChatMessage, ThreadSummary } from "@/types/domain";
import { formatDateTime } from "@/utils/format";

export const ChatCenterScreen = () => {
  const { profile } = useAuth();
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!profile) return;
    const loadThreads = async () => {
      const nextThreads = await listThreads(profile.companyId);
      setThreads(nextThreads);
      setThreadId(nextThreads[0]?.id ?? null);
    };
    loadThreads();
  }, [profile]);

  useEffect(() => {
    if (!threadId) return;
    const loadMessages = async () => {
      setMessages(await listMessages(threadId));
    };
    loadMessages();
  }, [threadId]);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === threadId) ?? null,
    [threads, threadId],
  );

  const handleSend = async () => {
    if (!profile || !threadId || !body.trim()) return;
    setSubmitting(true);
    await sendMessage({
      companyId: profile.companyId,
      threadId,
      senderId: profile.id,
      senderName: profile.fullName,
      body: body.trim(),
    });
    setBody("");
    setMessages(await listMessages(threadId));
    setSubmitting(false);
  };

  return (
    <ThemedScreen title="Chat Messenger" subtitle="Shared messaging for owners, dispatchers, and drivers">
      <AppCard title="Threads">
        {threads.length === 0 ? (
          <Text style={styles.secondaryText}>
            No chat threads found. Create company channels in Supabase to begin messaging.
          </Text>
        ) : (
          <View style={styles.threadRow}>
            {threads.map((thread) => (
              <Pressable
                key={thread.id}
                style={[styles.threadChip, thread.id === threadId ? styles.threadChipActive : null]}
                onPress={() => setThreadId(thread.id)}
              >
                <Text
                  style={[styles.threadChipText, thread.id === threadId ? styles.threadChipTextActive : null]}
                >
                  {thread.title}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </AppCard>

      <AppCard title={activeThread?.title ?? "Messages"}>
        <FlatList
          data={messages}
          keyExtractor={(item) => item.id}
          scrollEnabled={false}
          contentContainerStyle={styles.messagesList}
          renderItem={({ item }) => (
            <View style={styles.messageCard}>
              <Text style={styles.messageSender}>{item.sender_name}</Text>
              <Text style={styles.messageBody}>{item.body}</Text>
              <Text style={styles.messageMeta}>{formatDateTime(item.created_at)}</Text>
            </View>
          )}
          ListEmptyComponent={
            <Text style={styles.secondaryText}>No messages in this thread yet.</Text>
          }
        />
      </AppCard>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <AppCard title="New Message">
          <TextInput
            style={styles.input}
            placeholderTextColor={palette.textSecondary}
            value={body}
            onChangeText={setBody}
            placeholder="Type a message..."
            multiline
          />
          <PrimaryButton
            label="Send Message"
            onPress={handleSend}
            loading={submitting}
            disabled={!threadId || !body.trim()}
          />
        </AppCard>
      </KeyboardAvoidingView>
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  secondaryText: {
    color: palette.textSecondary,
    fontSize: 13,
  },
  threadRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  threadChip: {
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surfaceElevated,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  threadChipActive: {
    borderColor: palette.blue,
    backgroundColor: "rgba(59,130,246,0.2)",
  },
  threadChipText: {
    color: palette.textSecondary,
    fontSize: 12,
    fontWeight: "600",
  },
  threadChipTextActive: {
    color: palette.textPrimary,
  },
  messagesList: {
    gap: 8,
  },
  messageCard: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 10,
    backgroundColor: palette.surfaceElevated,
  },
  messageSender: {
    color: palette.textPrimary,
    fontWeight: "600",
    marginBottom: 4,
  },
  messageBody: {
    color: palette.textPrimary,
    fontSize: 14,
  },
  messageMeta: {
    color: palette.textSecondary,
    marginTop: 6,
    fontSize: 11,
  },
  input: {
    minHeight: 80,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surfaceElevated,
    color: palette.textPrimary,
    padding: 10,
    textAlignVertical: "top",
  },
});
