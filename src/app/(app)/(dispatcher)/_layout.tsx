import { Redirect, Tabs } from "expo-router";

import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

export default function DispatcherLayout() {
  const { profile } = useAuth();
  if (!profile) return null;
  if (profile.role !== "dispatcher") {
    return <Redirect href="/(app)" />;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: palette.surface,
          borderTopColor: palette.border,
        },
        tabBarActiveTintColor: palette.blue,
        tabBarInactiveTintColor: palette.textSecondary,
      }}
    >
      <Tabs.Screen
        name="dashboard"
        options={{ title: "Dashboard" }}
      />
      <Tabs.Screen
        name="drivers-status"
        options={{ title: "Drivers" }}
      />
      <Tabs.Screen
        name="communications-hub"
        options={{ title: "Comms" }}
      />
      <Tabs.Screen
        name="documents-center"
        options={{ title: "Docs" }}
      />
      <Tabs.Screen name="chat" options={{ title: "Chat" }} />
      <Tabs.Screen name="notifications" options={{ title: "Alerts" }} />
      <Tabs.Screen name="profile" options={{ title: "Profile" }} />
      <Tabs.Screen name="recommended-loads" options={{ href: null }} />
      <Tabs.Screen name="alerts-center" options={{ href: null }} />
      <Tabs.Screen name="broker-panel" options={{ href: null }} />
    </Tabs>
  );
}
