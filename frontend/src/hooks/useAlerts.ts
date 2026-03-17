/**
 * useAlerts — fetch paginated alerts from GET /api/alerts.
 *
 * Accepts optional severity filter and pagination parameters.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { AxiosError } from "axios";

import apiClient from "@/lib/api";
import type { PaginatedAlertResponse, Severity } from "@/types/api";

interface UseAlertsParams {
  limit?: number;
  offset?: number;
  severity?: Severity | null;
}

async function fetchAlerts(
  params: UseAlertsParams,
): Promise<PaginatedAlertResponse> {
  const { data } = await apiClient.get<PaginatedAlertResponse>("/api/alerts", {
    params: {
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
      ...(params.severity != null ? { severity: params.severity } : {}),
    },
  });
  return data;
}

export function useAlerts(
  params: UseAlertsParams = {},
): UseQueryResult<PaginatedAlertResponse, AxiosError> {
  return useQuery<PaginatedAlertResponse, AxiosError>({
    queryKey: ["alerts", params.limit, params.offset, params.severity],
    queryFn: () => fetchAlerts(params),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}
