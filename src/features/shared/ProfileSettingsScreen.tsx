import { StyleSheet, Text, View } from "react-native";

import { AppCard } from "@/components/AppCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemedScreen } from "@/components/ThemedScreen";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

export const ProfileSettingsScreen = () => {
  const { profile, signOut, refreshProfile, profileLoading } = useAuth();

  return (
    <ThemedScreen title="Profile & Settings" subtitle="Authenticated account details and controls">
      <AppCard title="User">
        <View style={styles.row}>
          <Text style={styles.label}>Name</Text>
          <Text style={styles.value}>{profile?.fullName ?? "-"}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Email</Text>
          <Text style={styles.value}>{profile?.email ?? "-"}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Role</Text>
          <Text style={styles.value}>{profile?.role ?? "-"}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Company</Text>
          <Text style={styles.value}>{profile?.companyId ?? "-"}</Text>
        </View>
      </AppCard>

      <AppCard title="Session">
        <PrimaryButton
          label="Refresh Profile"
          onPress={refreshProfile}
          loading={profileLoading}
          tone="secondary"
        />
        <PrimaryButton label="Sign Out" onPress={signOut} tone="danger" />
      </AppCard>
    </ThemedScreen>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 10,
  },
  label: {
    color: palette.textSecondary,
    fontSize: 13,
    fontWeight: "600",
  },
  value: {
    color: palette.textPrimary,
    fontSize: 14,
    flexShrink: 1,
    textAlign: "right",
  },
});
