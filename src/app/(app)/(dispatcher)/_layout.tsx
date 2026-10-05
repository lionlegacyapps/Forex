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
        options={{ title: "Dashboard", tabBarIcon: icon("grid-outline") }}
      />
      <Tabs.Screen
        name="drivers-status"
        options={{ title: "Drivers", tabBarIcon: icon("people-outline") }}
      />
      <Tabs.Screen
        name="communications-hub"
        options={{ title: "Comms", tabBarIcon: icon("radio-outline") }}
      />
      <Tabs.Screen
        name="documents-center"
        options={{ title: "Docs", tabBarIcon: icon("document-text-outline") }}
      />
      <Tabs.Screen name="chat" options={{ title: "Chat", tabBarIcon: icon("chatbubbles-outline") }} />
      <Tabs.Screen
        name="notifications"
        options={{ title: "Alerts", tabBarIcon: icon("notifications-outline") }}
      />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: icon("person-outline") }} />
      <Tabs.Screen name="recommended-loads" options={{ href: null }} />
      <Tabs.Screen name="alerts-center" options={{ href: null }} />
      <Tabs.Screen name="broker-panel" options={{ href: null }} />
    </Tabs>
  );
}
