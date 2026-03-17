/**
 * useNeighborhood — fetch N-hop neighborhood subgraph for a given IP.
 *
 * The query is disabled when `ip` is null or empty.
 * staleTime: 60 seconds — subgraphs are expensive to compute.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { AxiosError } from "axios";

import apiClient from "@/lib/api";
import type { NeighborhoodResponse } from "@/types/api";

async function fetchNeighborhood(
  ip: string,
  hops: number,
): Promise<NeighborhoodResponse> {
  const { data } = await apiClient.get<NeighborhoodResponse>(
    "/api/graph/neighborhood",
    { params: { ip, hops } },
  );
  return data;
}

export function useNeighborhood(
  ip: string | null,
  hops: number = 2,
): UseQueryResult<NeighborhoodResponse, AxiosError> {
  return useQuery<NeighborhoodResponse, AxiosError>({
    queryKey: ["neighborhood", ip, hops],
    queryFn: () => fetchNeighborhood(ip!, hops),
    enabled: ip != null && ip.trim().length > 0,
    staleTime: 60_000,
  });
}
