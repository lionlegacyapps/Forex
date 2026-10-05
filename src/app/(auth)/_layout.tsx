import { Redirect, Stack } from "expo-router";

import { useAuth } from "@/context/AuthContext";
import { AppLoadingScreen } from "@/features/shared/AppLoadingScreen";

export default function AuthLayout() {
  const { session, loading } = useAuth();

  if (loading) return <AppLoadingScreen message="Checking session..." />;
  if (session) return <Redirect href="/(app)" />;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
    </Stack>
  );
}
