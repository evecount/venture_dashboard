import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { CommandCenter } from "@/components/dashboard/command-center";
import "@/styles.css";

const queryClient = new QueryClient();

export function App() {
  const [authed, setAuthed] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("cybr_auth") === "true";
    }
    return false;
  });
  const [pwd, setPwd] = useState("");

  if (!authed) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white font-sans">
        <div className="w-[400px] rounded-xl border border-white/10 bg-zinc-900/50 p-8 shadow-2xl backdrop-blur-sm">
          <h2 className="mb-6 text-2xl font-bold tracking-tight text-zinc-100">Prototype Access</h2>
          <input
            type="password"
            placeholder="Enter access code..."
            className="w-full rounded-md bg-zinc-950/50 border border-white/10 px-4 py-3 text-white outline-none transition-colors focus:border-white/30"
            value={pwd}
            onChange={(e) => setPwd(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && pwd === "mamba2026") {
                localStorage.setItem("cybr_auth", "true");
                setAuthed(true);
              }
            }}
          />
          <button
            className="mt-4 w-full rounded-md bg-zinc-100 px-4 py-3 font-medium text-zinc-900 transition-colors hover:bg-white cursor-pointer"
            onClick={() => {
              if (pwd === "mamba2026") {
                localStorage.setItem("cybr_auth", "true");
                setAuthed(true);
              }
            }}
          >
            Enter Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <CommandCenter />
    </QueryClientProvider>
  );
}
