import "react-native-gesture-handler";

import { StyleSheet } from "react-native";
import { ThemeProvider } from "@react-navigation/native";
import { Slot } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { appTheme } from "@/constants/theme";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { usePushNotifications } from "@/hooks/usePushNotifications";

const AuthAwareSlot = () => {
  const { profile } = useAuth();
  usePushNotifications(profile);
  return <Slot />;
};

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <ThemeProvider value={appTheme}>
        <AuthProvider>
          <StatusBar style="light" />
          <AuthAwareSlot />
        </AuthProvider>
      </ThemeProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
});
