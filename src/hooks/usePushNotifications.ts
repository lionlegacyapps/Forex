import { useEffect } from "react";
import * as Notifications from "expo-notifications";

import { registerForPushNotificationsAsync } from "@/lib/notifications";
import { registerPushToken } from "@/services/notificationService";
import type { AppProfile } from "@/types/domain";

export const usePushNotifications = (profile: AppProfile | null) => {
  useEffect(() => {
    if (!profile) return;

    let mounted = true;
    let responseSubscription: Notifications.EventSubscription | null = null;
    let receiveSubscription: Notifications.EventSubscription | null = null;

    const setup = async () => {
      const token = await registerForPushNotificationsAsync();
      if (!mounted || !token) return;
      await registerPushToken({
        userId: profile.id,
        companyId: profile.companyId,
        token,
      });
    };

    setup();

    receiveSubscription = Notifications.addNotificationReceivedListener(() => {
      // Hook point for local in-app state updates when push arrives in foreground.
    });
    responseSubscription = Notifications.addNotificationResponseReceivedListener(() => {
      // Hook point for deep-linking to chat/load details in a follow-up iteration.
    });

    return () => {
      mounted = false;
      receiveSubscription?.remove();
      responseSubscription?.remove();
    };
  }, [profile]);
};
