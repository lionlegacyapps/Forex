import { useLocalSearchParams } from "expo-router";

import { LoadDetailsScreen } from "@/features/driver/LoadDetailsScreen";

export default function OwnerDriverLoadDetailsRoute() {
  const params = useLocalSearchParams<{ loadId: string }>();
  return <LoadDetailsScreen loadId={params.loadId} routeMode="ownerDriver" />;
}
