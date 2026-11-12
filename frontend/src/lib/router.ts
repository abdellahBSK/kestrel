// A tiny hash router: #/ (overview) and #/p/<team>/<tab>. Shareable, survives reloads, no dependency.

import { useSyncExternalStore } from "react";

export type Tab = "activity" | "agents" | "prs" | "backlog";
export type Route = { view: "overview" } | { view: "project"; team: string; tab: Tab };

const TABS: Tab[] = ["activity", "agents", "prs", "backlog"];

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "p" && parts[1]) {
    const tab = TABS.includes(parts[2] as Tab) ? (parts[2] as Tab) : "activity";
    return { view: "project", team: parts[1], tab };
  }
  return { view: "overview" };
}

export function href(route: Route): string {
  return route.view === "overview" ? "#/" : `#/p/${encodeURIComponent(route.team)}/${route.tab}`;
}

export function navigate(route: Route) {
  window.location.hash = href(route);
}

function subscribe(cb: () => void) {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}

let cachedHash = "";
let cachedRoute: Route = { view: "overview" };

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => {
    if (window.location.hash !== cachedHash) {
      cachedHash = window.location.hash;
      cachedRoute = parse(cachedHash);
    }
    return cachedRoute;
  });
}
