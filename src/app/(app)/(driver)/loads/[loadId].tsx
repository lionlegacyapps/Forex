import { useLocalSearchParams } from "expo-router";

import { LoadDetailsScreen } from "@/features/driver/LoadDetailsScreen";

export default function DriverLoadDetailsRoute() {
  const params = useLocalSearchParams<{ loadId: string }>();
  return <LoadDetailsScreen loadId={params.loadId} />;
}
