import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { palette } from "@/constants/theme";

type PrimaryButtonProps = {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  tone?: "primary" | "secondary" | "danger";
};

const toneMap = {
  primary: palette.blue,
  secondary: palette.surfaceElevated,
  danger: palette.red,
} as const;

export const PrimaryButton = ({
  label,
  onPress,
  disabled,
  loading,
  tone = "primary",
}: PrimaryButtonProps) => (
  <Pressable
    style={[
      styles.button,
      { backgroundColor: toneMap[tone], opacity: disabled ? 0.55 : 1 },
    ]}
    onPress={onPress}
    disabled={disabled || loading}
  >
    {loading ? (
      <View style={styles.loading}>
        <ActivityIndicator size="small" color={palette.textPrimary} />
      </View>
    ) : null}
    <Text style={styles.label}>{label}</Text>
  </Pressable>
);

const styles = StyleSheet.create({
  button: {
    minHeight: 42,
    borderRadius: 12,
    paddingHorizontal: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  label: {
    color: palette.textPrimary,
    fontWeight: "700",
    fontSize: 14,
  },
  loading: {
    marginRight: 4,
  },
});
