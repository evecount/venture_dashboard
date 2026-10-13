import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "VentureOS · Progress tracking for venture studio founders" },
      { name: "description", content: "VentureOS helps a venture studio's founders and mentors see real startup progress from Slack, GitHub and Google Calendar." },
    ],
  }),
  component: About,
});

function About() {
  return (
    <main style={{ maxWidth: "42rem", margin: "0 auto", padding: "3rem 1.25rem", fontFamily: "system-ui, sans-serif", lineHeight: 1.6 }}>
      <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>VentureOS</h1>
      <p style={{ fontSize: "1.1rem" }}>
        VentureOS is a progress tracker for the founders in our venture studio program, and for the mentors who support them.
      </p>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>What it does</h2>
      <ul>
        <li>Founders send quick updates to a Slack assistant instead of filling in forms. The assistant turns them into check-ins, milestones and goals.</li>
        <li>Founders can optionally connect <strong>GitHub</strong> (commits and pull requests) and <strong>Google Calendar</strong> (a count of meetings, and how many were with people outside the team) so progress is based on real work.</li>
        <li>Mentors see a live dashboard of which startups are on track, blocked or quiet, so they can help at the right moment.</li>
      </ul>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>Why it asks for Google Calendar access</h2>
      <p>
        Read-only access to calendar events, solely to count each founder&rsquo;s meetings per day and how many included
        someone outside their team. Event titles, descriptions and invitees are not stored. Founders choose whether to connect
        and can disconnect at any time.
      </p>

      <p style={{ marginTop: "1.5rem" }}>
        Read the full <a href="/privacy">privacy policy</a>. VentureOS is used by the founders and mentors of our program; the
        dashboard itself requires an invitation.
      </p>
    </main>
  );
}
