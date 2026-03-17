/**
 * useGraphStats — fetch aggregate graph statistics from GET /api/stats.
 *
 * Refreshes every 30 seconds via react-query staleTime.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { AxiosError } from "axios";

import apiClient from "@/lib/api";
import type { GraphStatsResponse } from "@/types/api";

async function fetchGraphStats(): Promise<GraphStatsResponse> {
  const { data } = await apiClient.get<GraphStatsResponse>("/api/stats");
  return data;
}

export function useGraphStats(): UseQueryResult<GraphStatsResponse, AxiosError> {
  return useQuery<GraphStatsResponse, AxiosError>({
    queryKey: ["graph-stats"],
    queryFn: fetchGraphStats,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}
