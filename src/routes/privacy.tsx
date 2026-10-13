import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/privacy")({
  head: () => ({ meta: [{ title: "Privacy · VentureOS" }] }),
  component: Privacy,
});

function Privacy() {
  return (
    <main style={{ maxWidth: "42rem", margin: "0 auto", padding: "3rem 1.25rem", fontFamily: "system-ui, sans-serif", lineHeight: 1.6 }}>
      <h1 style={{ fontSize: "1.75rem", fontWeight: 700 }}>Privacy</h1>
      <p style={{ marginBottom: "1rem" }}><a href="/about">About VentureOS</a></p>
      <p>
        VentureOS is the progress tracker for our venture studio program. It helps mentors see how each startup is
        doing so they can help at the right moment. This page explains what it keeps.
      </p>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>What we keep</h2>
      <ul>
        <li><strong>Profile:</strong> your name, your email, your startup and your role (founder or mentor).</li>
        <li><strong>Updates you give the Slack bot:</strong> check-ins, blockers, milestones, goals, tasks and the short summaries the bot writes from them.</li>
        <li><strong>GitHub (only if you connect it):</strong> for the repositories you choose, the repository name, who pushed, commit and pull request titles, and counts. We never read your code, and the connection is read-only.</li>
        <li><strong>Google Calendar (only if you connect it):</strong> per-day counts of meetings, and how many included someone outside your team. We do not store event titles, descriptions or who was invited. If you ask the bot "what's on my calendar?", it reads your events live to answer you and does not save them.</li>
      </ul>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>Who can see it</h2>
      <p>
        You, the other founders in your startup, and the program&rsquo;s mentors and coordinators. Mentor notes are visible to mentors only.
        Nothing is sold or shared with advertisers.
      </p>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>How it&rsquo;s protected</h2>
      <p>
        Connection tokens are encrypted in our database and only the bot can read them. Access links are signed and
        expire. Google data is used only to produce the meeting counts described above.
      </p>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>Google user data</h2>
      <p>
        VentureOS&rsquo;s use and transfer of information received from Google APIs adheres to the{" "}
        <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>,
        including the Limited Use requirements. Calendar access is read-only and is used only to count meetings as described above.
      </p>

      <h2 style={{ marginTop: "1.5rem", fontWeight: 600 }}>Your control</h2>
      <ul>
        <li>Disconnect GitHub or Google Calendar any time from your own account settings (GitHub: Applications; Google: Security, Third-party access).</li>
        <li>Ask the program coordinator to delete your data and we will remove it.</li>
      </ul>
    </main>
  );
}
