import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";

import { AppCard } from "@/components/AppCard";
import { InputField } from "@/components/InputField";
import { PrimaryButton } from "@/components/PrimaryButton";
import { palette } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

export const LoginScreen = () => {
  const { signInWithPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    const authError = await signInWithPassword(email.trim(), password);
    setLoading(false);
    if (authError) setError(authError);
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.root}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Lion Legacy Dispatch Mobile</Text>
        <Text style={styles.subtitle}>Secure access for drivers, dispatchers, and owners</Text>
      </View>

      <AppCard title="Sign In" description="Use your existing dispatching platform credentials.">
        <InputField
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="you@company.com"
        />
        <InputField
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="••••••••"
          error={error}
        />
        <PrimaryButton
          label="Login"
          loading={loading}
          onPress={handleLogin}
          disabled={!email || !password}
        />
      </AppCard>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 60,
    backgroundColor: palette.background,
    gap: 20,
  },
  header: {
    gap: 8,
  },
  title: {
    color: palette.textPrimary,
    fontSize: 28,
    fontWeight: "700",
  },
  subtitle: {
    color: palette.textSecondary,
    fontSize: 15,
  },
});
