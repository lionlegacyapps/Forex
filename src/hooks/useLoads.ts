import { useCallback, useEffect, useState } from "react";

import { listLoadsForProfile } from "@/services/loadService";
import type { AppProfile, LoadRecord } from "@/types/domain";

export const useLoads = (profile: AppProfile | null, asDriver = false) => {
  const [loads, setLoads] = useState<LoadRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    setLoads(await listLoadsForProfile(profile, { asDriver }));
    setLoading(false);
  }, [asDriver, profile]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { loads, loading, refresh };
};
