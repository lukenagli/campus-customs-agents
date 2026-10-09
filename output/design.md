# Campus Customs Dashboard: Design Notes

The goal: it should feel like the **back counter of a campus apparel shop**, not an admin panel. Yale blue (`#00356b`) carries authority and the brand. Warm paper and cork tones make it feel like a physical desk. Every visual metaphor maps to a real control, so the charm never costs usability.

## Layout (left → right, the way work flows)
| Column | What's there | Why |
|---|---|---|
| **Order board** (cork) | The 3 tickets as pinned paper slips | Work starts here. It mirrors the real ticket board. |
| **Back counter** | The 5 staff cards, the live **Shop floor** feed, then the **Shift report** | The middle is where the work happens. You watch it unfold. |
| **Register + checks** (sticky) | Cash register, then checks waiting for a signature | Money and approvals stay in view the whole time, because they're the human's job. |

Below 1180px the register and checks drop under the board. Below 760px everything stacks in work order: board → money → staff → feed. Nothing scrolls sideways.

## The staff (5 agents)
Each agent has its **own color, icon, and role line**, reused everywhere: the card's top band, the feed tags, tool chips, report cards, and handoff arrows.

| Agent | Look | Role line |
|---|---|---|
| Boss | 👔 Yale blue, larger card, gold "MANAGER" tag and gold ring | Shop manager · routes tickets, makes the final call |
| Inventory | 📦 green | Stockroom · stock, shortfalls, vendors |
| Accounting | 🧮 amber | Books · cash, invoices, margins |
| Facilities | 🔑 purple | Shop space · leases and rent |
| Customer Service | 💬 rose | Front counter · drafts replies |

- **Boss sits alone at the top**, with the specialists in a row below, so the org chart is obvious at a glance.
- **The active agent lifts and glows** in its own color, and its icon bobs. The card's status line says what it's doing ("Checking get_lease", "Waiting on Accounting", "✓ Reported back"). A small counter shows tool calls this run.
- **Handoffs are drawn as curved dashed arrows** between the cards, in the sender's color. The newest one animates with a small slip traveling along it, and a caption reads "Latest handoff: Facilities → Accounting". The arrows sit *behind* the cards so they never cover text.

## Live feed: a shop-floor conversation
- Every line is tagged with the agent's colored name pill.
- A handoff reads like a person passing a note ("Facilities hands off to Accounting"), and the task appears on a **dashed paper slip** in typewriter font.
- Each tool call is a small **monospace chip** (`🔧 get_lease lease_id=1`), followed by a "↩ data" chip when the result comes back. You can see the agents working from real data, not prose. Refusals show as red ⛔ chips.
- Boss's final call and your own approvals ("✍ You · Luke approved and paid request #1") end the thread.

## Tickets resolve with a rubber stamp
- Slips are lined order paper with a perforated top edge, a red pushpin, and a slight tilt. They straighten when hovered or selected.
- When a run finishes, a red **RESOLVED** stamp slams down (scale-in with a little overshoot, multiply-blended like real ink).
- If money is still waiting, a gold **"approval pending"** badge stays on the slip until the check is signed. "Resolved" means the team's work is done, and the badge says the human's part isn't.

## Approvals are checks waiting for a signature
- Each pending request is drawn as a **bank check**: security-pattern paper, "PAY TO THE ORDER OF Elm City Properties", the amount box, the amount in words, a memo, the requesting agent, and **"Cash after signing"**.
- **Signing:** the approver's name (default "Luke") is typed into a script-font "Signing as" line. Approving opens a confirm dialog showing the before and after balance. On success, the signature **writes itself** across the line and a green **PAID** stamp lands. Rejecting asks for a reason and stamps **VOID**.
- **Disabled when cash is short:** if the check is bigger than checking, the sign button is disabled with a plain explanation.
- **Refusals stay visible:** any refusal from the backend (for example, an agent name used as approver) appears in red on the check itself.

## Cash is a register
- The register is a dark unit with a **green LCD**. After a payment the number **counts down** (eased over about 1.4s) and glows amber while it drops, so the change is impossible to miss.
- A bar under it shows **pending approvals vs. cash**, with "After: $…". It turns red if what's pending exceeds the balance.
- Each payment prints on a short **receipt tape** with a zigzag tear and who signed it.

## Small touches
- A gold rule under the Yale-blue header, and a "CC" crest shaped like a shield.
- A blinking red **LIVE** tag while a run is going.
- The confirm dialog blurs the counter behind it.
- Respects `prefers-reduced-motion`.
- System fonts only (no CDN): Georgia for headings, Courier for paper, and Segoe Script for signatures. It loads instantly and works offline.

## Usability guardrails
- Contrast stays high: dark ink on paper, white on Yale blue, and an LCD green on near-black.
- One primary action per slip ("Hand to the team ▸"), which is hidden once resolved.
- Every money action is behind a confirm dialog.
- Reset is in the header, behind a confirm, and disabled while a run is active.
