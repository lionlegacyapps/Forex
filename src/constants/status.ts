import { palette } from "@/constants/theme";
import type { LoadStatus } from "@/types/domain";

type StatusStyle = {
  label: string;
  color: string;
};

const statusMap: Record<LoadStatus, StatusStyle> = {
  assigned: { label: "Assigned", color: palette.blue },
  in_transit: { label: "In Transit", color: palette.blue },
  arrived: { label: "Arrived", color: palette.orange },
  loaded: { label: "Loaded", color: palette.blue },
  delivered: { label: "Delivered", color: palette.green },
  empty: { label: "Empty", color: palette.green },
  warning: { label: "Warning", color: palette.orange },
  late: { label: "Late", color: palette.red },
  canceled: { label: "Canceled", color: palette.red },
};

export const getStatusStyle = (status: LoadStatus): StatusStyle =>
  statusMap[status] ?? { label: status, color: palette.textSecondary };

export const loadStatusUpdateOptions: Array<{
  status: LoadStatus;
  label: string;
}> = [
  { status: "arrived", label: "Arrived" },
  { status: "loaded", label: "Loaded" },
  { status: "delivered", label: "Delivered" },
  { status: "empty", label: "Empty" },
];
