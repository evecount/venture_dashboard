import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Wrench } from "lucide-react";

/** Account-menu entry for the Developer page. Renders nothing unless the server says this person is a developer. */
export function DeveloperLink() {
  const [dev, setDev] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/dash/session")
      .then((r) => r.json() as Promise<{ dev?: boolean }>)
      .then((b) => !cancelled && setDev(b.dev === true))
      .catch(() => null);
    return () => {
      cancelled = true;
    };
  }, []);
  if (!dev) return null;
  return (
    <Link
      to="/dev"
      className="flex w-full items-center gap-2 border-b border-border px-4 py-3 text-left text-sm hover:bg-secondary"
    >
      <Wrench size={15} /> Developer
    </Link>
  );
}
