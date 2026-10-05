import { supabase } from "@/lib/supabase";
import type { AppProfile, UserRole } from "@/types/domain";

type RawProfile = {
  id: string;
  role: string;
  company_id: string;
  first_name: string | null;
  last_name: string | null;
  is_owner_operator: boolean | null;
};

const normalizeRole = (role: string): UserRole => {
  if (role === "driver" || role === "dispatcher" || role === "owner") {
    return role;
  }
  return "driver";
};

export const fetchAppProfile = async (
  userId: string,
  email: string,
): Promise<AppProfile | null> => {
  const { data, error } = await supabase
    .from("profiles")
    .select("id, role, company_id, first_name, last_name, is_owner_operator")
    .eq("id", userId)
    .single<RawProfile>();

  if (error || !data) return null;

  const fullName = [data.first_name, data.last_name].filter(Boolean).join(" ");

  return {
    id: data.id,
    email,
    role: normalizeRole(data.role),
    companyId: data.company_id,
    fullName: fullName || email,
    isOwnerOperator: Boolean(data.is_owner_operator),
  };
};
