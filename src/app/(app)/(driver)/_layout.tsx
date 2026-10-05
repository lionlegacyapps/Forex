import { Redirect, Tabs } from "expo-router";

import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

export default function DriverLayout() {
  const { profile } = useAuth();
  if (!profile) return null;
  if (profile.role !== "driver") {
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
        name="loads"
        options={{ title: "Loads" }}
      />
      <Tabs.Screen
        name="status-updates"
        options={{ title: "Status" }}
      />
      <Tabs.Screen name="chat" options={{ title: "Chat" }} />
      <Tabs.Screen name="notifications" options={{ title: "Alerts" }} />
      <Tabs.Screen name="profile" options={{ title: "Profile" }} />
      <Tabs.Screen name="documents" options={{ href: null }} />
      <Tabs.Screen name="location-checkin" options={{ href: null }} />
    </Tabs>
  );
}
