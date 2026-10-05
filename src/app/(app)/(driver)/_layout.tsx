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
        options={{ title: "Dashboard", tabBarIcon: icon("grid-outline") }}
      />
      <Tabs.Screen
        name="loads"
        options={{ title: "Loads", tabBarIcon: icon("trail-sign-outline") }}
      />
      <Tabs.Screen
        name="status-updates"
        options={{ title: "Status", tabBarIcon: icon("checkmark-done-outline") }}
      />
      <Tabs.Screen name="chat" options={{ title: "Chat", tabBarIcon: icon("chatbubble-ellipses-outline") }} />
      <Tabs.Screen
        name="notifications"
        options={{ title: "Alerts", tabBarIcon: icon("notifications-outline") }}
      />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: icon("person-outline") }} />
      <Tabs.Screen name="documents" options={{ href: null }} />
      <Tabs.Screen name="location-checkin" options={{ href: null }} />
    </Tabs>
  );
}
