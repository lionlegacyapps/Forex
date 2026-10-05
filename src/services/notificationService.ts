import type { RealtimeChannel } from "@supabase/supabase-js";

import { supabase } from "@/lib/supabase";
import type { AlertRecord, AppProfile, NotificationEventType } from "@/types/domain";

export const listAlerts = async (profile: AppProfile): Promise<AlertRecord[]> => {
  const { data, error } = await supabase
    .from("alerts")
    .select("id, company_id, event_type, title, message, created_at, load_id")
    .eq("company_id", profile.companyId)
    .order("created_at", { ascending: false })
    .limit(50);

  if (error || !data) return [];
  return data as AlertRecord[];
};

export const subscribeToAlerts = (
  profile: AppProfile,
  onInsert: (alert: AlertRecord) => void,
): RealtimeChannel => {
  const channel = supabase.channel(`alerts-${profile.companyId}`);
  channel.on(
    "postgres_changes",
    {
      event: "INSERT",
      schema: "public",
      table: "alerts",
      filter: `company_id=eq.${profile.companyId}`,
    },
    (payload) => onInsert(payload.new as AlertRecord),
  );
  channel.subscribe();
  return channel;
};

export const registerPushToken = async (args: {
  userId: string;
  companyId: string;
  token: string;
}) => {
  await supabase.from("mobile_push_tokens").upsert(
    {
      user_id: args.userId,
      company_id: args.companyId,
      token: args.token,
      platform: "expo",
      updated_at: new Date().toISOString(),
    },
    { onConflict: "user_id,token" },
  );
};

export const emitNotificationEvent = async (args: {
  companyId: string;
  actorId: string;
  eventType: NotificationEventType;
  title: string;
  message: string;
  loadId?: string;
}) => {
  await supabase.from("alerts").insert({
    company_id: args.companyId,
    actor_id: args.actorId,
    event_type: args.eventType,
    title: args.title,
    message: args.message,
    load_id: args.loadId ?? null,
    created_at: new Date().toISOString(),
  });
};
