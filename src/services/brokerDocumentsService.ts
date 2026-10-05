import { supabase } from "@/lib/supabase";

export const sendDocumentToBrokerEmail = async (args: {
  companyId: string;
  loadId: string;
  brokerEmail: string;
  documentId: string;
  requestedBy: string;
}) => {
  const { data, error } = await supabase.functions.invoke("send-broker-document", {
    body: {
      companyId: args.companyId,
      loadId: args.loadId,
      brokerEmail: args.brokerEmail,
      documentId: args.documentId,
      requestedBy: args.requestedBy,
    },
  });

  if (error) {
    throw new Error(
      "Broker email integration is not configured yet. Connect this hook to your outbound email/automation service.",
    );
  }

  return data;
};
