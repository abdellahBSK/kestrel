import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });
}

export function useSession(team: string | null, id: string | null, live: boolean) {
  return useQuery({
    queryKey: ["session", team, id],
    queryFn: () => api.session(team!, id),
    enabled: !!team,
    refetchInterval: live ? 2500 : 15000,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === team ? prev : undefined),
  });
}
