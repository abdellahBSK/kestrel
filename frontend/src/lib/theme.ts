import { useCallback, useEffect, useState } from "react";

export type ThemePref = "system" | "light" | "dark";
const KEY = "kestrel.theme";

/** Which clock times are shown in: this computer's (the server's UTC offset) or the browser's zone. */
export type TimePref = "computer" | "browser";
const TZ_KEY = "kestrel.tz";

export function useTimePref() {
  const [pref, setPref] = useState<TimePref>(() => {
    try {
      return localStorage.getItem(TZ_KEY) === "browser" ? "browser" : "computer";
    } catch {
      return "computer";
    }
  });
  const set = useCallback((next: TimePref) => {
    try {
      localStorage.setItem(TZ_KEY, next);
    } catch {
      /* private mode: the choice lasts for this tab only */
    }
    setPref(next);
  }, []);
  return { pref, set };
}

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function apply(pref: ThemePref) {
  const dark = pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(read);

  useEffect(() => {
    apply(pref);
    if (pref !== "system") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);

  const set = useCallback((next: ThemePref) => {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode: the choice lasts for this tab only */
    }
    setPref(next);
  }, []);

  return { pref, set };
}
