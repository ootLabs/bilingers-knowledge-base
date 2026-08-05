# Quiz & certificate

> Status: **not implemented**, and the product decisions are still open — including whether the certificate is worth building at all.

## The intent

After learning from the assistant, the user checks their understanding with a short quiz. Passing can produce a certificate under the Bilingers.app patronage, confirming readiness to raise a child bilingually.

Explicitly a **soft** certificate for a parent or layperson — not an expert exam. The working shape is around 10 fundamental questions whose real job is to transmit the basics, not to filter people out.

## Open questions

- **Is the certificate actually valuable to a parent?** Raised inside the team and unresolved — one view is that the knowledge is the whole value and the certificate is decoration. Worth answering before building it, since it is the most complex part of this module.
- Number of questions, pass threshold, retry policy.
- Are questions hand-written by the foundation or generated from the knowledge base? Hand-written is more defensible for something that issues a certificate.
- Is the certificate a downloadable file, a shareable page, or just a screen?
- Does it carry a name? A name means personal data — see the GDPR bias in [`unanswered-questions.md`](unanswered-questions.md).
- Does passing unlock the discount on Bilingers.app for "Świadomy Rodzic"?

## Wording — the liability point

The certificate must never read as an assessment of parenting competence. It attests that someone completed a knowledge quiz on bilingualism. The distinction is the entire legal and ethical safety margin of this feature, and the final wording needs the foundation's approval before launch.

## Dependencies

- Question content depends on the knowledge base being settled ([`knowledge-base.md`](knowledge-base.md)).
- Any name on a certificate pulls in personal-data handling that the rest of the app avoids.

## When this gets built

Fill in: the final question set and where it lives, scoring rules, the approved certificate wording, and what data (if any) is stored per issued certificate.
