import { Redirect, Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

const icon = (name: keyof typeof Ionicons.glyphMap) => ({
  color,
  size,
}: {
  color: string;
  size: number;
}) => <Ionicons name={name} color={color} size={size} />;

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
        options={{ title: "Dashboard", tabBarIcon: icon("grid-outline") }}
      />
      <Tabs.Screen
        name="trucks-dashboard"
        options={{ title: "Trucks", tabBarIcon: icon("car-sport-outline") }}
      />
      <Tabs.Screen
        name="loads-overview"
        options={{ title: "Loads", tabBarIcon: icon("trail-sign-outline") }}
      />
      <Tabs.Screen
        name="documents-factoring"
        options={{ title: "Factoring", tabBarIcon: icon("document-attach-outline") }}
      />
      {profile.isOwnerOperator ? (
        <Tabs.Screen
          name="driver-view"
          options={{ title: "Driver View", tabBarIcon: icon("navigate-outline") }}
        />
      ) : (
        <Tabs.Screen name="driver-view" options={{ href: null }} />
      )}
      <Tabs.Screen name="chat" options={{ title: "Chat", tabBarIcon: icon("chatbubbles-outline") }} />
      <Tabs.Screen
        name="notifications"
        options={{ title: "Alerts", tabBarIcon: icon("notifications-outline") }}
      />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: icon("person-outline") }} />
      <Tabs.Screen name="truck-status" options={{ href: null }} />
      <Tabs.Screen name="driver-loads" options={{ href: null }} />
      <Tabs.Screen name="driver-status-updates" options={{ href: null }} />
      <Tabs.Screen name="driver-location-checkin" options={{ href: null }} />
      <Tabs.Screen name="driver-documents" options={{ href: null }} />
      <Tabs.Screen name="driver-load-details/[loadId]" options={{ href: null }} />
    </Tabs>
  );
}
