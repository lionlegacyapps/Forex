export type UserRole = "driver" | "dispatcher" | "owner";

export type LoadStatus =
  | "assigned"
  | "arrived"
  | "loaded"
  | "delivered"
  | "empty"
  | "in_transit"
  | "canceled"
  | "warning"
  | "late";

export type NotificationEventType =
  | "new_assigned_load"
  | "load_status_changed"
  | "driver_arrived"
  | "driver_loaded"
  | "driver_delivered"
  | "driver_empty"
  | "document_uploaded"
  | "new_chat_message"
  | "load_canceled"
  | "recommended_load_available";

export interface AppProfile {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  companyId: string;
  isOwnerOperator: boolean;
}

export interface LoadRecord {
  id: string;
  company_id: string;
  load_number: string;
  origin: string;
  destination: string;
  status: LoadStatus;
  driver_id?: string | null;
  dispatcher_id?: string | null;
  truck_id?: string | null;
  pickup_at?: string | null;
  delivery_at?: string | null;
  broker_name?: string | null;
}

export interface AlertRecord {
  id: string;
  company_id: string;
  event_type: NotificationEventType;
  title: string;
  message: string;
  created_at: string;
  load_id?: string | null;
}

export interface ChatMessage {
  id: string;
  company_id: string;
  sender_id: string;
  sender_name: string;
  body: string;
  created_at: string;
  thread_id: string;
}

export interface ThreadSummary {
  id: string;
  company_id: string;
  title: string;
  last_message_at: string | null;
}
