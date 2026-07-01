# LSD Builder — Interview Guide

This file defines the full pre-build interview flow. Read it before running any
interview. It covers Express mode, Guided mode, name proposal, the Socratic
exchange, and the source fit response taxonomy.

---

## Mode selection

Ask this once, at the start, before any other question:

> "Quick question before we start: do you want **Express mode** (three quick
> questions, then I build) or **Guided mode** (I fetch the source first, share
> what I find, and we talk through it before building)? Express is faster; Guided
> catches mismatches between what you want and what the source actually contains."

**When to recommend Express:**
- User has already provided URL + clear intent in the same message
- User is returning to add a second skill from the same domain
- User says anything like "just build it", "let's go", "quickly"

**When to recommend Guided:**
- Intent is vague ("make a skill from this")
- URL looks like a poor fit candidate (news, product page, homepage, social)
- Multiple URLs with potentially conflicting content
- User is building a skill they plan to share with others (higher quality bar)

---

## Express mode

Run all three questions in a single message, not one at a time. Keep it brief.

### Phase 1 — Three questions + name proposal

Ask all of these together:

1. **Intent:** "What do you want an agent to be able to do with this skill?"
   *(one sentence is enough — this becomes the drift anchor)*

2. **Key concepts:** "Are there specific concepts, terms, or sections in this
   source that are most important to preserve? If not, I'll use what I find."

3. **Audience:** "Who will use this skill — just you, a team, or are you planning
   to share it more widely?" *(affects how conservative the caveats and update
   policy should be)*

After the user answers, do a quick pre-fetch of the URL to get the title and
source type (this takes a few seconds; you can do it while reviewing their
answers). Then propose a name:

> "I was thinking **`<proposed-slug>`** — does that work, or would you prefer
> something different?"

Slug construction rules:
- Derive from the source title + skill type (e.g. `wikipedia-ai-signals`,
  `stripe-api-guide`, `react-hooks-reference`)
- Lowercase, alphanumeric + hyphens only, max 40 chars (leave headroom)
- No consecutive hyphens, no leading/trailing hyphens
- If the user's intent strongly suggests a different name than the title implies,
  lean toward the intent: `ai-writing-detector` over `wikipedia-signs-of-ai-writing`

If the user proposes their own name, validate it silently against the slug rules
and flag any issues before building.

Then build immediately. No more questions.

---

## Guided mode

### Phase 1 — Three questions (same as Express)

Ask the same three questions. While the user is reading/answering, fetch the URL
in parallel. By the time they reply, you should have:
- Source title and type
- Fit scores (overall_fit, rule_density, procedure_density, example_density)
- Opportunity map (candidate skill types)
- Whether the source has low-fit signals (see taxonomy below)

### Phase 2 — Post-fetch Socratic exchange

Present your read of the source before the user has committed to anything. This
is the core of Guided mode. The format:

> "I've read the source. Here's what I found:
>
> **What it actually covers:** [one sentence — what the source is mainly about]
>
> **Strongest skill fit:** [skill type] (fit: [overall_fit], [rule/procedure/example density])
>
> **Other options I see:** [list from opportunity map, with confidence]
>
> **Potential mismatch:** [only if there is one — 'You said X, but the source is
> mostly about Y. The best skill here would do Z instead. Is that still useful?']"

Then ask **at most two** Socratic questions. Not open-ended — targeted. Examples:

- "The source covers [broad topic] but you said you want [narrow thing]. Should
  I scope the skill to [narrow thing] and treat the rest as background, or build
  for the full source?"
- "This source has [high rule density / low procedure density]. The skill will be
  better as a checklist/reference than a step-by-step workflow. Is that what you had in mind?"
- "Sources 2 and 3 have a direct contradiction on [topic]. Before I build, which
  do you want to treat as authoritative?"

**Depth limit: two turns.** After two exchanges, close with:

> "Got it. I have what I need — let me build."

Do not ask a third Socratic question. If genuinely uncertain after two turns,
flag it as an open question in the skill's `motivation.md` for the user to
resolve later.

### Name proposal (Guided mode)

Propose the name at the end of Phase 2, after the Socratic exchange, just before
building. By this point you know the actual content and the user's confirmed
intent, so the name can be more precise than in Express mode:

> "I'm going to name this **`<proposed-slug>`** — it reflects [what the source
> covers] + [what you said you want to do with it]. Any changes?"

---

## The Socratic mode rationale — one paragraph for users who ask

If the user asks why there are two modes or what Guided mode is for:

> "Guided mode exists because skill quality depends on the match between what you
> intend and what the source actually contains. A good interviewer doesn't just
> take your brief at face value — they read the material, form a view, and
> challenge assumptions that won't survive contact with the source. But that only
> works if the challenge is quick and targeted, not an open-ended seminar. Guided
> mode gives you one or two pointed questions after the source has been read, then
> gets out of the way."

---

## Motivation capture — write this to disk before building

Before running `lsd build`, write a `motivation.json` to the intended output
directory (create it if it doesn't exist). This record survives rebuilds and is
the drift anchor for future `lsd check` decisions.

```json
{
  "intent": "<user's one-sentence answer to Q1>",
  "audience": "<user's answer to Q3>",
  "key_concepts": ["<concept 1>", "<concept 2>"],
  "skill_name_confirmed": "<final agreed slug>",
  "build_mode": "express | guided",
  "socratic_notes": "<any open questions flagged during Guided exchange, or null>",
  "recorded_at": "<ISO-8601 timestamp>"
}
```

Pass the motivation to the build via `--motivation-file ./my-skill/motivation.json`
when that flag is available. Until it is, write the file to the output directory
before building so it is included in the package.

The `intent` field is the most important. It is what `lsd check` will present to
the user when substantial source drift is detected: "When you created this skill,
you said: [intent]. The source has changed substantially. Does it still serve that
purpose?"

---

## Source fit gate — responses by failure type

After fetching, if any of the following signals appear, **do not build immediately**.
Present the signal and ask the user how to proceed. These checks apply in both
Express and Guided mode; in Express mode insert them between Phase 1 and the build.

| Signal | How to detect | What to say |
|---|---|---|
| **Login / paywall** | HTTP 200 but word count < 200 and body contains "sign in" / "log in" / "create an account" | "This URL requires a login — I can only see the gate, not the content. Options: paste the text directly, try a public cached version, or use a different URL." |
| **Transactional page** | overall_fit = none/low, no procedure/rule density, content is price/spec/review structured data | "This looks like a product or listing page rather than a how-to or reference. It doesn't have the procedures or rules that make a useful skill. Try the documentation or FAQ section instead?" |
| **Index / nav page** | High link density, low prose density, content is mostly a table of contents | "This is an index page — the real content is one level deeper. Should I build from a specific article linked here, or try the full docs section?" |
| **Too broad / encyclopedic** | overall_fit = medium, specificity = low, topic is a major domain term | "This source covers a broad topic and the skill would be quite generic. A more specific page — a tutorial, a how-to, a process document — would produce a better skill. Want to try a more specific URL, or continue with this one?" |
| **Purely informational** | procedure_density = low, rule_density = low, content is news/press/narrative | "This source describes something but doesn't explain how to do it — it's informational rather than procedural. The skill would be more of a reference card than an active guide. Continue, or try a how-to version of this topic?" |
| **Fetch failed** | HTTP 4xx / 5xx / timeout | "I couldn't access this URL ([status]). It may be private, moved, or temporarily down. Try a different URL, or check the fallback chain in source-policy.md if you have a previous build." |

**Never hard-block.** Always offer to continue. Some of the most interesting
skills come from non-obvious sources. The user needs to acknowledge the risk, but
the decision is theirs.

---

## Multi-source considerations

When the user provides two or more URLs:

- Run all the Phase 1 questions once, not per URL.
- In Guided mode, after fetching all sources, lead with the conflict summary:
  "I found [N] conflicts across your sources. The most significant: [worst one].
  Do you want to resolve any of these before I build, or should I flag them in
  the skill and let you decide later?"
- The name proposal covers the combined skill, not individual sources.
  Suggest a name that reflects the synthesis, e.g. `react-typescript-patterns`
  rather than `react-docs-plus-typescript-handbook`.
- If any single source has a low-fit signal, flag it individually — a weak source
  degrades the whole multi-source build.

---

## What not to do

- Do not ask more than three Phase 1 questions (intent, key concepts, audience).
- Do not ask the name question before you have fetched the source — you need the
  title and fit type to propose a good slug.
- Do not run more than two Socratic turns in Guided mode.
- Do not block the build if the user says "just go ahead" at any point.
- Do not ask the same question twice in different phrasings.
- Do not treat low source fit as a hard block — always offer to continue.
