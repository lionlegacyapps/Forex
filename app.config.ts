import type { ConfigContext, ExpoConfig } from "expo/config";

const APP_NAME = "Lion Legacy Dispatch Mobile";
const APP_SLUG = "lionlegacy-dispatch-mobile";
const APP_SCHEME = "dispatchmobile";
const IOS_BUNDLE_ID = "com.lionlegacy.dispatchmobile";
const ANDROID_PACKAGE = "com.lionlegacy.dispatchmobile";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: APP_NAME,
  slug: APP_SLUG,
  scheme: APP_SCHEME,
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "dark",
  ios: {
    supportsTablet: true,
    bundleIdentifier: IOS_BUNDLE_ID,
  },
  android: {
    package: ANDROID_PACKAGE,
    adaptiveIcon: {
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
      backgroundColor: "#0B1220",
    },
    predictiveBackGestureEnabled: false,
  },
  web: {
    favicon: "./assets/favicon.png",
    bundler: "metro",
  },
  plugins: [
    "expo-router",
    "expo-font",
    [
      "expo-splash-screen",
      {
        image: "./assets/splash-icon.png",
        resizeMode: "contain",
        backgroundColor: "#0B1220",
      },
    ],
    [
      "expo-notifications",
      {
        icon: "./assets/icon.png",
        color: "#3B82F6",
      },
    ],
  ],
  extra: {
    ...config.extra,
    eas: {
      projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID ?? "",
    },
  },
  experiments: {
    typedRoutes: true,
  },
});
