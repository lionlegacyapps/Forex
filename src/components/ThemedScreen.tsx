import { type PropsWithChildren, type ReactNode } from "react";
import {
  ActivityIndicator,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { palette } from "@/constants/theme";

type ThemedScreenProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
  rightContent?: ReactNode;
  loading?: boolean;
  scrollable?: boolean;
}>;

export const ThemedScreen = ({
  title,
  subtitle,
  rightContent,
  loading,
  scrollable = true,
  children,
}: ThemedScreenProps) => {
  const content = loading ? <ActivityIndicator color={palette.blue} size="large" /> : children;

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
        {rightContent ? <View>{rightContent}</View> : null}
      </View>
      {scrollable ? (
        <ScrollView
          style={styles.body}
          contentContainerStyle={styles.bodyContent}
          showsVerticalScrollIndicator={false}
        >
          {content}
        </ScrollView>
      ) : (
        <View style={[styles.body, styles.bodyContent]}>{content}</View>
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: palette.background,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: palette.border,
  },
  headerText: { flex: 1 },
  title: {
    color: palette.textPrimary,
    fontSize: 24,
    fontWeight: "700",
  },
  subtitle: {
    color: palette.textSecondary,
    marginTop: 4,
    fontSize: 14,
  },
  body: {
    flex: 1,
    backgroundColor: palette.background,
  },
  bodyContent: {
    padding: 16,
    gap: 12,
  },
});
