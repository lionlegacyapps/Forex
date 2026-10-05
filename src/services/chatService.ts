import { supabase } from "@/lib/supabase";
import type { ChatMessage, ThreadSummary } from "@/types/domain";

export const listThreads = async (companyId: string): Promise<ThreadSummary[]> => {
  const { data, error } = await supabase
    .from("chat_threads")
    .select("id, company_id, title, last_message_at")
    .eq("company_id", companyId)
    .order("last_message_at", { ascending: false })
    .limit(20);

  if (error || !data) return [];
  return data as ThreadSummary[];
};

export const listMessages = async (threadId: string): Promise<ChatMessage[]> => {
  const { data, error } = await supabase
    .from("chat_messages")
    .select("id, company_id, sender_id, sender_name, body, created_at, thread_id")
    .eq("thread_id", threadId)
    .order("created_at", { ascending: true })
    .limit(100);

  if (error || !data) return [];
  return data as ChatMessage[];
};

export const sendMessage = async (args: {
  companyId: string;
  threadId: string;
  senderId: string;
  senderName: string;
  body: string;
}) => {
  const createdAt = new Date().toISOString();
  await supabase.from("chat_messages").insert({
    company_id: args.companyId,
    thread_id: args.threadId,
    sender_id: args.senderId,
    sender_name: args.senderName,
    body: args.body,
    created_at: createdAt,
  });

  await supabase
    .from("chat_threads")
    .update({ last_message_at: createdAt })
    .eq("id", args.threadId);
};
