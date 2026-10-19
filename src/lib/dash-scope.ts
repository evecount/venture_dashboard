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
