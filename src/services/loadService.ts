import { supabase } from "@/lib/supabase";
import type { AppProfile, LoadRecord, LoadStatus } from "@/types/domain";

const baseLoadSelect =
  "id, company_id, load_number, origin, destination, status, driver_id, dispatcher_id, truck_id, pickup_at, delivery_at, broker_name";

export const listLoadsForProfile = async (
  profile: AppProfile,
  options?: { asDriver?: boolean },
): Promise<LoadRecord[]> => {
  const query = supabase
    .from("loads")
    .select(baseLoadSelect)
    .eq("company_id", profile.companyId)
    .order("pickup_at", { ascending: true });

  if (profile.role === "driver" || options?.asDriver) {
    query.eq("driver_id", profile.id);
  } else if (profile.role === "dispatcher") {
    query.eq("dispatcher_id", profile.id);
  }

  const { data, error } = await query;
  if (error || !data) return [];
  return data as LoadRecord[];
};

export const getLoadById = async (loadId: string): Promise<LoadRecord | null> => {
  const { data, error } = await supabase
    .from("loads")
    .select(baseLoadSelect)
    .eq("id", loadId)
    .single();
  if (error || !data) return null;
  return data as LoadRecord;
};

export const updateLoadStatus = async (args: {
  loadId: string;
  status: LoadStatus;
  updatedBy: string;
  companyId: string;
}) => {
  const timestamp = new Date().toISOString();

  await supabase
    .from("loads")
    .update({
      status: args.status,
      updated_at: timestamp,
    })
    .eq("id", args.loadId)
    .eq("company_id", args.companyId);

  await supabase.from("load_status_events").insert({
    load_id: args.loadId,
    company_id: args.companyId,
    status: args.status,
    updated_by: args.updatedBy,
    created_at: timestamp,
  });
};

export const sendLocationCheckin = async (args: {
  loadId: string;
  companyId: string;
  userId: string;
  latitude: number;
  longitude: number;
}) => {
  await supabase.from("load_location_checkins").insert({
    load_id: args.loadId,
    company_id: args.companyId,
    user_id: args.userId,
    latitude: args.latitude,
    longitude: args.longitude,
    created_at: new Date().toISOString(),
  });
};
