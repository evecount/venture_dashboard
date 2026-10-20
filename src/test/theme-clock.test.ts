import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { themeCore } from "@/components/theme-clock";

const SG = [1.3521, 103.8198] as const;
const at = (hhmm: string, day = "2026-10-20") => Date.parse(`${day}T${hhmm}:00+08:00`);
const sgt = (t: number) => new Date(t + 8 * 3_600_000).toISOString().slice(11, 16);

let core: ReturnType<typeof themeCore>;
beforeAll(() => {
  core = themeCore();
});
beforeEach(() => localStorage.clear());

describe("sun times", () => {
  it("matches Singapore's published times for 20 Oct 2026 (to within two minutes)", () => {
    const s = core.sun(at("12:00"), ...SG);
    expect(sgt(s.sunrise)).toMatch(/^06:4[7-9]$/);
    expect(sgt(s.sunset)).toMatch(/^18:5[2-4]$/);
    expect(s.dusk - s.sunset).toBeGreaterThan(15 * 60_000); // civil dusk: the sun fully set, ~20 min later
  });
});

describe("time-of-day theme", () => {
  const phase = (hhmm: string) => core.phase(at(hhmm), ...SG, 480);

  it("is plain day from 8am to 6pm", () => {
    for (const h of ["08:00", "12:00", "17:59"])
      expect(phase(h)).toMatchObject({ dark: false, warm: 0 });
  });

  it("warms gradually from 6pm to sunset, then stays warm until the sun has fully set", () => {
    const a = phase("18:10");
    const b = phase("18:40");
    expect(a.dark).toBe(false);
    expect(a.warm).toBeGreaterThan(0);
    expect(b.warm).toBeGreaterThan(a.warm);
    expect(phase("19:05")).toMatchObject({ dark: false, warm: 1 });
  });

  it("is night from dusk to dawn, then warm, easing back to day by 8am", () => {
    expect(phase("19:30")).toMatchObject({ dark: true });
    expect(phase("03:00")).toMatchObject({ dark: true });
    expect(phase("06:40")).toMatchObject({ dark: false, warm: 1 });
    const m = phase("07:30");
    expect(m.warm).toBeGreaterThan(0);
    expect(m.warm).toBeLessThan(1);
  });

  it("changes by only a sliver each minute during the evening drift", () => {
    expect(phase("18:31").warm - phase("18:30").warm).toBeLessThan(0.025);
  });
});

describe("the red mark is an hour hand", () => {
  // Local wall-clock time, whatever timezone the tests run in.
  const local = (h: number, m = 0) => new Date(2026, 9, 20, h, m).getTime();
  it("points at the hour, the same for am and pm", () => {
    expect(core.hourAngle(local(0))).toBe(0); // 12 o'clock
    expect(core.hourAngle(local(1))).toBe(30); // 1am → 1 o'clock
    expect(core.hourAngle(local(13))).toBe(30); // 1pm → 1 o'clock
    expect(core.hourAngle(local(15))).toBe(90); // 3 o'clock
    expect(core.hourAngle(local(21))).toBe(270); // 9 o'clock
  });
  it("creeps with the minutes, half a degree each", () => {
    expect(core.hourAngle(local(13, 30))).toBe(45);
    expect(core.hourAngle(local(13, 31)) - core.hourAngle(local(13, 30))).toBe(0.5);
  });
  it("is what the knob shows, manual choice or not", () => {
    expect(core.resolve(local(13)).angle).toBe(30);
    localStorage.setItem(core.KEY, JSON.stringify({ theme: "dark", until: local(23) }));
    expect(core.resolve(local(13))).toMatchObject({ dark: true, manual: true, angle: 30 });
  });
});

describe("clicking the knob", () => {
  it("holds a choice until the clock catches up, then automatic carries on", () => {
    const noon = at("12:00");
    const until = core.nextFlip(noon);
    expect(core.clock(until).dark).toBe(true); // tonight's dusk: the clock now agrees with "night"
    localStorage.setItem(core.KEY, JSON.stringify({ theme: "dark", until }));
    expect(core.resolve(noon)).toMatchObject({ dark: true, manual: true });
    expect(core.resolve(until + 60_000).manual).toBe(false);
  });

  it("ignores an old-style or expired choice", () => {
    localStorage.setItem(core.KEY, "dark");
    expect(core.resolve(at("12:00")).manual).toBe(false);
    localStorage.setItem(core.KEY, JSON.stringify({ theme: "dark", until: at("11:00") }));
    expect(core.resolve(at("12:00")).manual).toBe(false);
  });
});
