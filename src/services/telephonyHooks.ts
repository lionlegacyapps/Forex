type TelephonyProvider = "twilio" | "telnyx" | "vapi";

type BrokerActionPayload = {
  loadId: string;
  brokerPhone: string;
  note?: string;
};

const notImplemented = (provider: TelephonyProvider, action: string) => {
  throw new Error(
    `Telephony hook not configured: ${provider} ${action}. Wire this to your server-side integration.`,
  );
};

export const telephonyHooks = {
  callBroker: async (provider: TelephonyProvider, payload: BrokerActionPayload) => {
    void payload;
    notImplemented(provider, "call");
  },
  textBroker: async (provider: TelephonyProvider, payload: BrokerActionPayload) => {
    void payload;
    notImplemented(provider, "text");
  },
};
