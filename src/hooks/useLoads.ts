import { useCallback, useEffect, useState } from "react";

import { listLoadsForProfile } from "@/services/loadService";
import type { AppProfile, LoadRecord } from "@/types/domain";

export const useLoads = (profile: AppProfile | null, asDriver = false) => {
  const [loads, setLoads] = useState<LoadRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    const nextLoads = await listLoadsForProfile(profile, { asDriver });
    setLoads(nextLoads);
    setLoading(false);
  }, [asDriver, profile]);

  useEffect(() => {
    let cancelled = false;
    if (!profile) return;

    const loadInitially = async () => {
      const nextLoads = await listLoadsForProfile(profile, { asDriver });
      if (!cancelled) {
        setLoads(nextLoads);
      }
    };

    loadInitially();
    return () => {
      cancelled = true;
    };
  }, [asDriver, profile]);

  return { loads, loading, refresh };
};
