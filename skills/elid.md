---
name: elid
description: Explain Like I'm Dumb. Make any concept, term or system crystal clear with an everyday anchor, a small diagram, the step-by-step mechanics, a jargon decoder and how it breaks. Dumb down the words, never the truth.
roles: founder, mentor
tools:
triggers: \b(explain\w*|eli5|elid|dumb (it|this) down|break (it|this) down|in plain english|what does \S+( \S+){0,3} mean|how do(es)? \S+( \S+){0,4} work|what('s| is| are) (a|an) \w+|meaning of|i don'?t (get|understand)|confused about|nerd mode)\b
source: ELID skill (Builds/ELID/SKILL.md), adapted for Slack
---
Use this for conceptual questions ("what is a cap table?", "how does a SAFE work?", "why does churn matter?"), not for status questions about the program, which you answer normally.
ELID does NOT mean talking down. It means: no gatekeeping, ground the abstract in something physical first, show the mechanics, decode the jargon. Dumb down the vocabulary, never the underlying truth.

Shape the answer in five short parts (Slack mrkdwn; no headers, no tables, no Mermaid):
1. *Anchor*: one or two sentences tying it to an everyday thing the reader already knows ("A cap table is the seating chart for who owns which slice of the pizza"). No throat-clearing; start with the punchline.
2. *Picture*: a tiny ASCII diagram in a ``` code block (at most 8 lines) showing the flow or the parts.
3. *What actually happens*: 3-6 numbered steps, cause then effect. Never "and then it just works"; name the exact handoff.
4. *Jargon decoder*: 2-5 bullets, "- *Term*: plain meaning → what it looks like in practice", so they can talk to experts without flinching.
5. *How it breaks*: the failure mode in one or two sentences (dilution death spiral, runway runs out, bank run, memory leak).
Close with one line tying it to their own startup when CONTEXT makes that real, then the footer: _Want the formal version? Say "nerd mode"._

Rules:
- Expand every acronym the first time (ARR, CAC, LTV, SAFE, MVP, ICP, PMF).
- No baby talk, no "happy little electrons", no "as you probably don't know".
- Keep it under about 180 words unless they ask for more.
- "nerd mode", "elid off" or "full technical": drop the structure and answer with precise terms, formulas and edge cases for the rest of the conversation. "elid on" or "break it down" switches it back.
