# Working agreements

How this project is run. Read alongside `PROJECT_STATE.md` at the start of every
session.

## How to reply

1. **End every reply with the next step.** Without fail. One clear action the
   stakeholder should take next, stated plainly — not a menu of options.
2. **Put content in the reply, not pointers to it.** If a document section is
   worth reading, paste it. "See §5" is not an answer. Files are the durable
   record; the reply must stand on its own.
3. **Explain a concept before using it.** What it is, why it exists, why it
   matters here, an example. No unexplained jargon — BRD, ADR, aggregate,
   invariant, idempotency and the rest all get defined in `docs/glossary.md`
   before they appear anywhere else.
4. **Lead with what changed or what is wrong**, not with a recap of what is
   already settled.

## How decisions are made

5. **Never silently fill a business gap.** If something affects the product and
   has not been stated, ask — or state the assumption loudly and mark it
   TO VALIDATE. Recorded guesses are fine; hidden ones are not.
6. **Challenge, don't just comply.** If a request conflicts with an earlier
   decision, with the scale of the organization, or with itself, say so and
   explain the trade-off. Then do what the stakeholder decides.
7. **Significant decisions become ADRs** in `docs/adr/` — context, options
   considered, decision, consequences, and what would make us revisit it.
8. **Requirements are never silently rewritten.** Show OLD, NEW, REASON, IMPACT,
   and what it affects downstream.

## How the work is sequenced

9. **Business before technology.** Requirements justify technology, never the
   reverse.
10. **Simplest thing that meets the requirement.** No Kubernetes, Kafka,
    microservices, Redis or GraphQL without a demonstrated need. Configurability
    is deferred decision-making and costs 3–5× a fixed rule — for a ~15-person
    single organization, prefer the fixed rule and record where the seam goes.
11. **Build vertically when building starts.** Feature → database → API → logic
    → UI → test. A working product at every stage, not a backend followed by a
    frontend.
12. **No code until implementation is explicitly approved.**

## Project-specific standing rules

13. **Derive, don't ask** (ADR-001). If the system needs a number, compute it
    from something the user already does. Only ask when it cannot be derived,
    and then make answering optional.
14. **Judge every design decision against recording friction.** Nothing is
    tracked today (K-007), so the product creates a habit rather than replacing
    one. Anything that makes recording more expensive threatens every number the
    system produces.
15. **Every displayed number must be explainable** (BR-020). Metrics are derived,
    so the derivation must be inspectable. A number a lead cannot interrogate
    will not be trusted, and should not be.

## Git

- Branch: `claude/dev-resource-planning-discovery-djziba`
- Commit after each meaningful unit of work, with reasoning in the message.
- No pull request unless explicitly asked for.
