import { supabase } from "@/lib/supabase";

export const listRecommendedLoads = async (companyId: string) => {
  const { data, error } = await supabase
    .from("recommended_loads")
    .select(
      "id, load_number, origin, destination, score, reason, created_at, status, company_id",
    )
    .eq("company_id", companyId)
    .order("created_at", { ascending: false })
    .limit(20);

  if (error || !data) return [];
  return data as Array<{
    id: string;
    load_number: string;
    origin: string;
    destination: string;
    score: number | null;
    reason: string | null;
    status: string | null;
    created_at: string;
    company_id: string;
  }>;
};
