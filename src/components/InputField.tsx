import { StyleSheet, Text, TextInput, type TextInputProps, View } from "react-native";

import { palette } from "@/constants/theme";

type InputFieldProps = TextInputProps & {
  label: string;
  error?: string | null;
};

export const InputField = ({ label, error, ...inputProps }: InputFieldProps) => (
  <View style={styles.wrapper}>
    <Text style={styles.label}>{label}</Text>
    <TextInput
      style={[styles.input, error ? styles.inputError : null]}
      placeholderTextColor={palette.textSecondary}
      {...inputProps}
    />
    {error ? <Text style={styles.error}>{error}</Text> : null}
  </View>
);

const styles = StyleSheet.create({
  wrapper: {
    gap: 6,
  },
  label: {
    color: palette.textSecondary,
    fontSize: 13,
    fontWeight: "600",
  },
  input: {
    backgroundColor: palette.surfaceElevated,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.border,
    color: palette.textPrimary,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  inputError: {
    borderColor: palette.red,
  },
  error: {
    color: palette.red,
    fontSize: 12,
  },
});
