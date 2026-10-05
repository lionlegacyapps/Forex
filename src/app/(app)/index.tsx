import { Redirect } from "expo-router";

import { useAuth } from "@/context/AuthContext";

export default function AppIndexRoute() {
  const { profile } = useAuth();

  if (!profile) return null;

  if (profile.role === "driver") return <Redirect href="/(app)/(driver)/dashboard" />;
  if (profile.role === "dispatcher") return <Redirect href="/(app)/(dispatcher)/dashboard" />;
  return <Redirect href="/(app)/(owner)/dashboard" />;
}
