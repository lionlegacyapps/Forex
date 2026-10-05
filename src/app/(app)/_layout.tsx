import { Redirect, Stack } from "expo-router";

import { useAuth } from "@/context/AuthContext";
import { AppLoadingScreen } from "@/features/shared/AppLoadingScreen";

export default function AppLayout() {
  const { session, profile, loading, profileLoading } = useAuth();

  if (loading) return <AppLoadingScreen message="Loading application..." />;
  if (!session) return <Redirect href="/(auth)/login" />;
  if (profileLoading) return <AppLoadingScreen message="Loading user profile..." />;
  if (!profile) return <AppLoadingScreen message="Profile not found. Contact your administrator." />;

  return <Stack screenOptions={{ headerShown: false }} />;
}
