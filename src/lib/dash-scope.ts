// Pure rules for what the dashboard server may show or accept. Shared by the routes and tests.

type TaskLike = { owner_slack_id: string | null };

/**
 * Tasks a viewer may see, without the owner's Slack id (the browser never needs it). Mentors see every task. A founder
 * sees unowned tasks and their own team's, never a mentor's private follow-ups (same rule as the Slack bot).
 */
export function visibleTasks<T extends TaskLike>(
  tasks: T[],
  role: "mentor" | "founder",
  teamSlackIds: Iterable<string>,
): Omit<T, "owner_slack_id">[] {
  const team = new Set(teamSlackIds);
  return tasks
    .filter((t) => role === "mentor" || !t.owner_slack_id || team.has(t.owner_slack_id))
    .map(({ owner_slack_id: _owner, ...rest }) => rest);
}

/** A GitHub installation may be linked when it is new, or already belongs to the same startup (a reconnect). */
export function canLinkInstallation(
  existing: { startup_id: string } | null | undefined,
  startupId: string,
): boolean {
  return !existing || existing.startup_id === startupId;
}

/**
 * What the GitHub callback may copy from the parked install record (written by the webhook before the founder's browser
 * returns). Only a brand-new link uses it: once an installation is linked, its live repo list is kept current by the
 * webhook and the bot, and the parked copy goes stale (a reconnect must not roll the repos back to the first install).
 */
export function parkedInstallFields(
  parked: { account: string | null; repos: string[] | null } | null | undefined,
  alreadyLinked: boolean,
): { account?: string | null; repos?: string[] } {
  if (!parked || alreadyLinked) return {};
  return { account: parked.account, repos: parked.repos ?? [] };
}
