<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- Keep dashboard demo records in a browser-safe data module and all dashboard colors in semantic global CSS tokens, so presentation stays consistent and independent of future live integrations.
- Keep this command center frontend-only until live integrations are explicitly requested; label simulated connection and data clearly.
- Model studio responsibilities and demo perspectives in the browser-safe fixtures; perspective switching is presentation only, never an authorization mechanism.
