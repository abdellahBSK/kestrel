import { afterEach, describe, expect, it } from "vitest";
import { clock, dateTime, duration, offsetLabel, relative, setDisplayOffset, tokens, usd } from "./format";

describe("estimated dollars", () => {
  it("shows cents, whole dollars past $100, and crumbs as <$0.01", () => {
    expect(usd(0)).toBe("$0");
    expect(usd(0.004)).toBe("<$0.01");
    expect(usd(3.456)).toBe("$3.46");
    expect(usd(1234.5)).toBe("$1,235");
    expect(usd(null)).toBe("–");
  });
});

const TS = "2026-11-12T08:49:43Z"; // UTC

afterEach(() => setDisplayOffset(null));

describe("times at a fixed UTC offset (this computer's clock)", () => {
  it("shows UTC times shifted by the computer's offset, whatever the browser thinks", () => {
    setDisplayOffset(60);
    expect(clock(TS)).toBe("09:49:43");
    expect(clock(TS, false)).toBe("09:49");
    setDisplayOffset(0);
    expect(clock(TS)).toBe("08:49:43");
  });

  it("handles negative and half-hour offsets and day boundaries", () => {
    setDisplayOffset(-300);
    expect(clock("2026-11-12T02:00:00Z", false)).toBe("21:00");
    setDisplayOffset(330);
    expect(clock(TS, false)).toBe("14:19");
    setDisplayOffset(60);
    expect(dateTime("2026-11-12T23:30:00Z")).toMatch(/13/); // already the next day at UTC+1
  });

  it("labels offsets", () => {
    expect(offsetLabel(60)).toBe("UTC+01:00");
    expect(offsetLabel(-330)).toBe("UTC−05:30");
    expect(offsetLabel(0)).toBe("UTC+00:00");
  });
});

describe("timezone-free formats", () => {
  it("formats relative times and durations from UTC instants", () => {
    const now = new Date("2026-11-12T10:00:00Z").getTime();
    expect(relative("2026-11-12T09:59:30Z", now)).toBe("just now");
    expect(relative("2026-11-12T09:30:00Z", now)).toBe("30m ago");
    expect(relative("2026-11-12T05:00:00Z", now)).toBe("5h ago");
    expect(relative("2026-11-11T09:00:00Z", now)).toBe("yesterday");
    expect(duration("2026-11-12T08:49:43Z", "2026-11-12T09:04:39Z")).toBe("14m 56s");
    expect(duration("2026-11-12T08:00:00Z", "2026-11-12T10:05:00Z")).toBe("2h 05m");
    expect(duration(null, TS)).toBe("–");
  });

  it("abbreviates token counts", () => {
    expect(tokens(950)).toBe("950");
    expect(tokens(74_108)).toBe("74k");
    expect(tokens(1_360_000)).toBe("1.36M");
    expect(tokens(undefined)).toBe("0");
  });

  it("returns nothing for missing or invalid timestamps", () => {
    expect(clock(null)).toBe("");
    expect(clock("not a date")).toBe("");
  });
});
