import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Moon, Sun } from "lucide-react";

export type Theme = "light" | "dark";

const KEY = "vd_theme";

/**
 * Runs in <head> before the page paints: the saved choice, else the device's setting. Keeps the dark theme from
 * flashing white on load. Kept tiny and dependency-free because it's inlined as a string.
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem("${KEY}");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";var d=document.documentElement;d.classList.toggle("dark",t==="dark");d.style.colorScheme=t;}catch(e){}})();`;

function currentTheme(): Theme {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark")
    ? "dark"
    : "light";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

function savedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

/**
 * Day/night dial for everyone: a disc that turns 180° (clockwise into night, back anticlockwise into day) on a
 * spring curve, quick off the mark and settling exactly on the pointer. The page changes with a circular reveal
 * from the dial where supported.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  // Starts as "light" on the server; the real value is read after mount (the boot script already applied it).
  const [theme, setTheme] = useState<Theme>("light");
  const [ready, setReady] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setTheme(currentTheme());
    setReady(true);
    // Follow the device setting until someone picks a theme, and keep other tabs in step.
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onMedia = () => {
      if (savedTheme()) return;
      const t: Theme = media.matches ? "dark" : "light";
      applyTheme(t);
      setTheme(t);
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key !== KEY) return;
      const t = savedTheme() ?? (media.matches ? "dark" : "light");
      applyTheme(t);
      setTheme(t);
    };
    media.addEventListener("change", onMedia);
    window.addEventListener("storage", onStorage);
    return () => {
      media.removeEventListener("change", onMedia);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode: still switches for this visit */
    }
    const swap = () => {
      applyTheme(next);
      setTheme(next);
    };
    const doc = document as Document & {
      startViewTransition?: (cb: () => void) => { ready: Promise<void> };
    };
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!doc.startViewTransition || reduced) {
      swap();
      return;
    }
    const box = ref.current?.getBoundingClientRect();
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

  const dark = theme === "dark";
  return (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label={dark ? "Switch to day mode" : "Switch to night mode"}
      title={dark ? "Day mode" : "Night mode"}
      className={`theme-toggle ${ready ? "" : "no-anim"} ${className}`}
      onClick={toggle}
    >
      {/* The disc turns 180°: sun under the pointer by day, moon by night. Everything else stays still. */}
      <span className="dial-bezel" aria-hidden="true" />
      <span className="dial-disc" aria-hidden="true">
        <span className="dial-half dial-day">
          <Sun className="dial-sun" size={13} strokeWidth={2.6} />
        </span>
        <span className="dial-half dial-night">
          <Moon className="dial-moon" size={12} strokeWidth={2.6} />
          <span className="dial-star dial-star-1" />
          <span className="dial-star dial-star-2" />
          <span className="dial-star dial-star-3" />
        </span>
      </span>
      <span className="dial-glass" aria-hidden="true" />
      <span className="dial-pointer" aria-hidden="true" />
    </button>
  );
}
