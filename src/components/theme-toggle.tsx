import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { themeCore, type ThemeState } from "./theme-clock";

export { THEME_BOOT_SCRIPT } from "./theme-clock";

const TICK_MS = 60_000;

/** Shortest turn from one angle to another, so the knob keeps going clockwise through the day (359° → 0°). */
function turnTo(from: number, to: number, dir?: 1 | -1): number {
  let d = (((to - from) % 360) + 360) % 360; // 0..359, clockwise
  if (dir === -1) d -= 360;
  else if (dir !== 1 && d > 180) d -= 360;
  return from + d;
}

function setKnob(angle: number) {
  document.documentElement.style.setProperty("--knob-angle", `${angle}deg`);
}

/** Run `swap` under the circular reveal from the knob, or instantly when that isn't available. */
function reveal(el: HTMLElement | null, swap: () => void) {
  const doc = document as Document & {
    startViewTransition?: (cb: () => void) => { ready: Promise<void> };
  };
  if (!doc.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    swap();
    return;
  }
  const box = el?.getBoundingClientRect();
  const x = box ? box.left + box.width / 2 : innerWidth - 40;
  const y = box ? box.top + box.height / 2 : 32;
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const t = doc.startViewTransition(() => flushSync(swap));
  void t.ready
    .then(() =>
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
        {
          duration: 600,
          easing: "cubic-bezier(0.4, 0, 0.2, 1)",
          pseudoElement: "::view-transition-new(root)",
        },
      ),
    )
    .catch(() => undefined);
}

/**
 * Day/night knob for everyone. It follows the time of day (see theme-clock.ts): the red mark creeps round
 * through the evening as the page warms, and turns to night once the sun has fully set — one clockwise turn per
 * day. A click flips day/night on the spring curve (clockwise into night, anticlockwise back to day) and holds
 * until the clock catches up with the choice; clicking back to what the clock says returns to automatic.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [state, setState] = useState<ThemeState | null>(null);
  const angle = useRef(0);
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const core = themeCore();
    angle.current =
      parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--knob-angle")) || 0;

    const sync = () => {
      const r = core.resolve();
      const wasDark = document.documentElement.classList.contains("dark");
      angle.current = turnTo(angle.current, r.angle);
      const swap = () => {
        core.apply(r);
        setKnob(angle.current);
        setState(r);
      };
      // Crossing into or out of night is the one visible moment; the warm drift is a tiny step each minute.
      if (wasDark !== r.dark) reveal(ref.current, swap);
      else swap();
    };
    sync();
    const timer = setInterval(sync, TICK_MS);
    const onVisible = () => document.visibilityState === "visible" && sync();
    const onStorage = (e: StorageEvent) => e.key === core.KEY && sync();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("storage", onStorage);

    // Use the device's location for sunset if the browser already allows it (never asks).
    void navigator.permissions
      ?.query({ name: "geolocation" as PermissionName })
      .then((p) => {
        if (p.state !== "granted") return;
        navigator.geolocation.getCurrentPosition((pos) => {
          try {
            localStorage.setItem(
              core.POS,
              JSON.stringify({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
            );
          } catch {
            /* fall back to the studio's location */
          }
          sync();
        });
      })
      .catch(() => undefined);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  function toggle() {
    const core = themeCore();
    const now = Date.now();
    const toDark = !core.resolve(now).dark;
    try {
      // Back to what the clock says: automatic again. Otherwise hold until the clock catches up with the choice.
      if (core.clock(now).dark === toDark) localStorage.removeItem(core.KEY);
      else
        localStorage.setItem(
          core.KEY,
          JSON.stringify({ theme: toDark ? "dark" : "light", until: core.nextFlip(now) }),
        );
    } catch {
      /* private mode: switches for this visit only */
    }
    const r = core.resolve(now);
    const shown = {
      ...r,
      dark: toDark,
      warm: toDark ? 0 : r.warm,
      angle: r.dark === toDark ? r.angle : toDark ? 180 : 0,
    };
    angle.current = turnTo(angle.current, shown.angle, toDark ? 1 : -1);
    reveal(ref.current, () => {
      core.apply(shown);
      setKnob(angle.current);
      setState(shown);
    });
  }

  const dark = state?.dark ?? false;
  const until = state
    ? new Date(state.next).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "";
  const label = dark ? "Switch to day mode" : "Switch to night mode";
  const title = state
    ? `${dark ? "Night" : state.warm > 0 ? "Evening light" : "Day"} · ${
        state.manual
          ? `your choice until ${until}`
          : `follows the time of day · changes at ${until}`
      }`
    : label;
  return (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label={label}
      title={title}
      className={`theme-toggle ${state ? "" : "no-anim"} ${className}`}
      onClick={toggle}
    >
      {/* A knob in a recessed well. The knob (grip ridge + red mark) turns; the well and the lighting on top
          stay still, like a real knob under a lamp. */}
      <span className="knob" aria-hidden="true">
        <span className="knob-face">
          <span className="knob-ridge" />
          <span className="knob-mark" />
        </span>
      </span>
      <span className="knob-light" aria-hidden="true" />
    </button>
  );
}
