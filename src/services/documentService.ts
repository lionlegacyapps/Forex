import * as DocumentPicker from "expo-document-picker";

import { supabase } from "@/lib/supabase";

const DOCUMENT_BUCKET = "load-documents";

export const uploadLoadDocumentFromDevice = async (args: {
  loadId: string;
  companyId: string;
  userId: string;
  documentType: string;
}) => {
  const picked = await DocumentPicker.getDocumentAsync({
    copyToCacheDirectory: true,
    multiple: false,
  });

  if (picked.canceled) return null;
  const asset = picked.assets[0];
  if (!asset) return null;

  const response = await fetch(asset.uri);
  const blob = await response.blob();
  const extension = asset.name.split(".").pop() ?? "bin";
  const path = `${args.companyId}/${args.loadId}/${Date.now()}-${args.documentType}.${extension}`;

  const { error } = await supabase.storage
    .from(DOCUMENT_BUCKET)
    .upload(path, blob, { upsert: true, contentType: asset.mimeType ?? undefined });
  if (error) throw error;

  await supabase.from("load_documents").insert({
    company_id: args.companyId,
    load_id: args.loadId,
    uploaded_by: args.userId,
    document_type: args.documentType,
    file_path: path,
    file_name: asset.name,
    created_at: new Date().toISOString(),
  });

  return path;
};

export const listLoadDocuments = async (args: {
  loadId: string;
  companyId: string;
}) => {
  const { data, error } = await supabase
    .from("load_documents")
    .select("id, file_name, document_type, file_path, created_at")
    .eq("company_id", args.companyId)
    .eq("load_id", args.loadId)
    .order("created_at", { ascending: false });

  if (error || !data) return [];
  return data as Array<{
    id: string;
    file_name: string;
    document_type: string;
    file_path: string;
    created_at: string;
  }>;
};

export const getDocumentDownloadUrl = async (path: string) => {
  const { data } = await supabase.storage
    .from(DOCUMENT_BUCKET)
    .createSignedUrl(path, 60 * 10);
  return data?.signedUrl ?? null;
};
