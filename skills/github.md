---
name: github
description: Connect GitHub, choose which repositories are tracked, and read what was actually built (commits, PRs, issues).
roles: mentor, founder
tools: connect_github, choose_repos, set_repos, github_activity
triggers: \b(github|git|repo|repos|repository|repositories|commit\w*|pull requests?|prs?|merged?|code|coding|shipp?\w*|built|build\w*)\b
---
- Founders: to connect GitHub or share their work, call connect_github. To switch or narrow which repository is tracked ("track the Bazi one", "watch all my repos"), call choose_repos. It only works with repositories already shared with the app; if one isn't shared, it gives them the link to share it. They never need to revoke the app.
- Mentors: set_repos chooses which of a startup's shared repositories are tracked.
- github_activity lists the real commits, pull requests and issues for a startup's tracked repositories (headlines and commit messages). Use it for "what did they ship / build / work on", and quote what is there. Never invent activity.
- Only tracked repositories count. If GitHub is connected but nothing is tracked yet, say so and tell the founder to pick one on their Home tab (or ask you to track it).
