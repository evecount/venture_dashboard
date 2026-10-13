// Server-only Supabase REST helper using the service-role key (Worker secret). Never import this from client code.

type Env = { url: string; key: string };

function env(): Env | null {
  const url = process.env["SUPABASE_URL"] ?? process.env["VITE_SUPABASE_URL"];
  const key = process.env["SUPABASE_SERVICE_ROLE_KEY"];
  return url && key ? { url, key } : null;
}

export async function admin<T = unknown>(
  path: string,
  init: { method?: string; body?: unknown; prefer?: string } = {},
): Promise<{ ok: boolean; status: number; data: T | null }> {
  const e = env();
  if (!e) return { ok: false, status: 500, data: null };
  const res = await fetch(`${e.url}/rest/v1/${path}`, {
    method: init.method ?? "GET",
    headers: {
      apikey: e.key,
      authorization: `Bearer ${e.key}`,
      "content-type": "application/json",
      ...(init.prefer ? { prefer: init.prefer } : {}),
    },
    ...(init.body !== undefined ? { body: JSON.stringify(init.body) } : {}),
  });
  const text = await res.text();
  return { ok: res.ok, status: res.status, data: text ? (JSON.parse(text) as T) : null };
}
