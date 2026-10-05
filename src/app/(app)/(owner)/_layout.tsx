import { Redirect, Tabs } from "expo-router";

import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

export default function OwnerLayout() {
  const { profile } = useAuth();
  if (!profile) return null;
  if (profile.role !== "owner") return <Redirect href="/(app)" />;

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
        name="trucks-dashboard"
        options={{ title: "Trucks" }}
      />
      <Tabs.Screen
        name="loads-overview"
        options={{ title: "Loads" }}
      />
      <Tabs.Screen
        name="documents-factoring"
        options={{ title: "Factoring" }}
      />
      {profile.isOwnerOperator ? (
        <Tabs.Screen
          name="driver-view"
          options={{ title: "Driver View" }}
        />
      ) : (
        <Tabs.Screen name="driver-view" options={{ href: null }} />
      )}
      <Tabs.Screen name="chat" options={{ title: "Chat" }} />
      <Tabs.Screen name="notifications" options={{ title: "Alerts" }} />
      <Tabs.Screen name="profile" options={{ title: "Profile" }} />
      <Tabs.Screen name="truck-status" options={{ href: null }} />
      <Tabs.Screen name="driver-loads" options={{ href: null }} />
      <Tabs.Screen name="driver-status-updates" options={{ href: null }} />
      <Tabs.Screen name="driver-location-checkin" options={{ href: null }} />
      <Tabs.Screen name="driver-documents" options={{ href: null }} />
      <Tabs.Screen name="driver-load-details/[loadId]" options={{ href: null }} />
    </Tabs>
  );
}
