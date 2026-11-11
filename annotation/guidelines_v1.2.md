# Annotation guidelines v1.2 (main study) - FROZEN 2026-11-09

Project: AzDistortion, checking news reports of official announcements against the source.
Status: v1.2 FROZEN (2026-11-09; distortion_type field added before any test labelling, see D2 (f); approved by the project owner; final check checks/guide12c.codex.md) = v1.1 plus the headline rule (section 3a), three clarifications from the calibration round, and process rules for the main study (fixed claim split, minutes per pair, own decisions). Label definitions and the decision order are unchanged. The changes beyond the headline rule are listed as prereg deviation D2. v1 history: Changes from v0.2: new label MISREPRESENTED, NOT_ADDRESSED renamed NOT_IN_SOURCE, A now includes the full decision text, tags extended with `inference`.

## 0. What you get for each pair

- **A**: the official announcement: the press release PLUS the full decision or legal text it announces (consolidated rule text where available), and any tariff table. Always use the frozen copy in `data/raw/announcements/<ann_id>/`, not the live page.
- **N**: one news item about A (headline + lead + body), frozen copy in `data/raw/news/<news_id>/`.

Work on one pair at a time. Write the minutes you spent on each pair in the `minutes` column (read them from a clock or timer when you start and finish the pair).

Human annotators (R1, R2): the labels must be your own decision. You may use any tool to open, convert or save the files, but do not ask an AI tool to suggest, fill in or check labels, tags or notes.

## 1. Step 1: list A's key conditions BEFORE reading N

Read A only. In `key_conditions` write 3-8 short lines, one per condition that decides who is affected and how:

- who is affected or obligated (e.g. "payer: acquiring bank")
- amounts, rates, bands, units
- dates: decision date, effective date, deadlines
- scope: which system, product or group
- exceptions (e.g. "salary, pension, benefit transfers excluded")
- status: adopted / draft / proposal / recommendation

Do not change this list after you read N. It is used for the omission flag.

## 2. Step 2: split N into claims

A **claim** is one checkable statement about A (one fact).

**Main study:** the claims are already split and fixed (the same claims are labelled by all humans and models), so do not merge, split or delete them; use clarification 2 in section 3a for a badly split claim. The rules below describe how the split was made.

- One number, one actor, one date per claim where possible. "From 1 April fees of 3 qəpik to 4 manat apply" = two claims (date; fee range).
- Each band of a list can be one claim, or the whole list one claim if it is copied as a block. Prefer one claim per row when the rows differ in the source.
- Do NOT make claims from: quotes of experts or citizens, questions to readers ("Fikirlərinizi şərhlərdə yazın"), background about other events, unless they state a fact about A.
- Mark the headline claims with `in_headline = 1`.

## 3. Step 3: label each claim against A (labels v1)

| Label | Use when | Example |
|---|---|---|
| SUPPORTED | A entails the claim. Paraphrase, rounding, unit conversion and one simple calculation are fine. | "Up to 100 manat - 3 qəpik" |
| CONTRADICTED | A addresses the point and the claim and A cannot both be true (explicit conflict of amount, actor, date, scope or status). | "Fee for 1,000-10,000 manat is 1 manat" when A says 0.5 AZN |
| MISREPRESENTED | A addresses the point, the claim is not strictly incompatible with A, but a reader who believes it gets a wrong picture of what A says: (a) status or certainty upgraded (plan/proposal/"is planned" reported as decided or certain; "may" as "must"); (b) scope widened or narrowed (a subgroup reported as everybody, or the reverse); (c) an explanation or consequence that misreads A's rule (reversed direction, wrong group affected); (d) a condition dropped inside the claim so that its meaning changes. | (hypothetical) "Free school meals WILL start in 2027" when A says "it is planned to start them"; "pensioners will receive a bonus" when A says "pensioners over 80" |
| NOT_IN_SOURCE | A does not settle the claim, and the claim does not distort anything A says: background, figures from other sources, previous-year data, history, expert or outlet opinion, compatible inferences. Not an error. | (hypothetical) "Last year the figure was 10 mln" when A gives only this year's figure |
| UNASSESSABLE | Too vague to check, a question, or A itself is unclear. Excluded from scores. | "The rules are getting stricter" |

Decision rules (in this order):

1. **Does A talk about this point at all?** No -> NOT_IN_SOURCE. Yes -> 2.
2. **Does A state it (directly or by one simple calculation)?** Yes -> SUPPORTED. No -> 3.
3. **Can the claim and A both be true at once?** No -> CONTRADICTED. Yes -> 4.
4. **Would a reader who believes the claim hold a false belief about what A says** (status, certainty, scope, direction, who is affected)? Yes -> MISREPRESENTED. No -> NOT_IN_SOURCE.

Further rules:

- Missing detail alone is not an error. "From 1 April" without the year is SUPPORTED if the year is clear from context.
- Rounding or a shorter wording that keeps the meaning is SUPPORTED, not MISREPRESENTED.
- A news claim that repeats a simplification made by A's own press release is SUPPORTED (cause = copied); note the simplification in `note`.
- A strong headline wording that is still compatible with A is labelled at claim level by rule 4; also consider the framing flag (step 4). Purely evaluative words around a checkable core are handled by section 3a, headline rule 4.
- If A was amended, label against the version valid on N's publication date.
- If you hesitate between two labels for more than 1 minute, choose the milder one (NOT_IN_SOURCE over MISREPRESENTED, MISREPRESENTED over CONTRADICTED), set `unsure = 1` and write why.

For every SUPPORTED, CONTRADICTED or MISREPRESENTED claim, paste the **evidence**: the sentence of A or the table cell.

For every MISREPRESENTED claim, also set `distortion_type` (one value) to the type that best describes how the picture becomes wrong:
- `status`: a plan, proposal or possibility reported as decided or certain, or "may" as "must" (case (a) above);
- `scope`: a narrower or wider group, product or system than in A (case (b));
- `actor`: a misleading picture of who pays, benefits or is obligated, without an actor that is incompatible with A being stated;
- `inference`: an explanation or consequence that misreads A's rule (case (c));
- `dropped_condition`: a condition dropped inside the claim so that its meaning changes (case (d)).
If two types apply, choose the one a reader would notice first and name the other in `note`. The content tags in section 4 are set as well; they are a separate field.

## 3a. Headlines, text parts and three clarifications (new in v1.2)

**Text parts.** headline = the title of N; lead = the first paragraph of N; body = the rest. Each claim keeps its part.

**Headline rule.** A headline claim is labelled by the same 4 steps as any other claim. In addition:
1. *Missing detail.* A headline is short. A condition the headline does not mention is not an error by itself. Example (calibration N0017-C01): "Azərbaycanda ƏDV-nin depozit hesabından DSMF-yə vəsait köçürmək imkanı yaradılıb", when A is the adopted law that creates this option from 1 January 2027 for some taxpayers: the option was created by an adopted law, so SUPPORTED. The missing group and start date are not errors here, because the headline does not name a group or say that the option already applies.
2. *Wrong group named.* If the headline names a group, the group is checked: a narrower group in A than in the headline is MISREPRESENTED (scope).
3. *Status and time.* Separate three cases:
   - A says adopted, in force later; the headline says adopted or "will": SUPPORTED.
   - A says planned or proposed; the headline says it is decided or certain ("daxil ediləcək" when A says "planlaşdırır"): MISREPRESENTED (status). If the upgrade is copied from A's own headline, the label is still MISREPRESENTED with cause = copied and unsure = 1 (section 8, decision 3).
   - A gives a later start date; the headline says it applies already: go to step 3. If both cannot be true, CONTRADICTED (date).
4. *Evaluative words.* Words such as "YENİ DÖVR" or "BÖYÜK" are not claims by themselves. If the headline has a checkable core, label the core by steps 1-4 and ignore the evaluative word in the label. Use the framing flag (step 4) when the evaluative wording pushes a conclusion A does not support. A headline with no checkable core is UNASSESSABLE. Worked example (calibration N0010-C01): "Avtomobillərin icbari sığortasında YENİ DÖVR - bəzi sürücülərə BÖYÜK GÜZƏŞTLƏR ediləcək". The core is "some drivers will get discounts"; A gives a 5% discount for drivers without accidents, so the core is SUPPORTED; whether "BÖYÜK GÜZƏŞTLƏR" misleads is decided with the framing flag.

**Clarification 1, simplification copied from the press release (rule v1.1).** If N repeats a simplification that is in A's own press release (T1), the claim is SUPPORTED with cause = copied, even when the full decision text (T2) is narrower. The exception is a status upgrade in A's own headline, which follows headline rule 3 and section 8, decision 3. Write the narrower T2 wording in `note`. This covers only what is in T1; details N adds from elsewhere are labelled by steps 1-4. Example (calibration N0010-C05): T1 says "zərər vuran şəxslərin sığorta haqlarına hər zərər vurduqları hadisəyə görə 30% əlavə tətbiq olunur"; N says "Hər törədilən qəzaya görə növbəti sığorta 30% bahalaşacaq". T2 applies the 30% to the history coefficient and only for at-fault paid claims, but the simplification is in T1: SUPPORTED, cause = copied.

**Clarification 2, a claim that bundles two facts.** If a claim has two facts with different labels, label it by the more serious one (CONTRADICTED, then MISREPRESENTED, then NOT_IN_SOURCE, then SUPPORTED). If one part is UNASSESSABLE, use the label of the other part. Set `split_error = 1` (a column in the claims sheet; 0 otherwise) and write both parts and their labels in `note`.

**Clarification 3, facts A does not state.** A date, actor or number that A (T1 and T2) does not state, and that does not distort a point A addresses, is NOT_IN_SOURCE, even when it is probably true. Example (calibration N0017-C02): "Milli Məclis qanunu iyulun 13-də qəbul edib, Prezident təsdiqləyib". A gives the law's date (13 iyul 2026) and the President's signature, but not the day Milli Məclis voted. "Prezident təsdiqləyib" is SUPPORTED, while "Milli Məclis adopted it on 13 July" is NOT_IN_SOURCE, so by clarification 2 the claim is NOT_IN_SOURCE with split_error = 1. A simple derivation from A (section 8, decision 2) is still SUPPORTED.

## 4. Content tags (for CONTRADICTED and MISREPRESENTED, several allowed)

- `amount`: amount, rate, threshold, band, unit
- `actor`: payer, beneficiary, obligated party, issuer
- `date`: effective date, deadline, period
- `scope`: wider or narrower group, product or system than in A
- `status`: draft/proposal/plan as adopted or certain; "may" as "must"; recommendation as obligation
- `inference`: an explanation or consequence that misreads A's rule

Optional cause tag (`cause`): `section_conflation`, `copied` (same error as the source or an earlier outlet, including A's own headline), `unknown`.

## 5. Step 4: pair flags

- `omission = 1` if N states the rule but drops a key condition from step 1 that **changes who is affected** (e.g. drops "salary and pension transfers are excluded"). Shortening without that effect is not omission. Write which condition in `omission_note`.
- `framing = 1` if the headline or lead pushes readers to a conclusion that A does not support, without a CONTRADICTED claim. Example: "Commission will be charged on card-to-card transfers" when the fee is on the acquiring bank. Write it in `framing_note`.

## 6. What not to do

- Do not use outside knowledge to label. Only A decides.
- Do not look at the other annotator's labels or at LLM labels.
- Do not edit `key_conditions` after reading N.
- Do not label by outlet reputation.

## 7. Pilot reporting (fill in at the end of the pilot)

- Minutes per pair and per claim (median).
- Hardest decisions (list 5 real cases).
- Proposed changes to labels and tags.

## 8. Standing decisions (from v0.2, updated)

1. A = press release + the full decision/legal text it announces, when publicly available. Details that exist in neither are NOT_IN_SOURCE (or MISREPRESENTED if they distort a point A addresses).
2. One simple calculation from A counts as SUPPORTED; write note = "derived".
3. A's own headline is part of A. If A's headline and body differ, label against the body and set unsure = 1. A news claim that copies a distorted A headline is still labelled against the body; add cause = copied.
4. News published before A is fine if it reports the same decision.
5. Outlet explanations ("Yəni ...") stating a consequence about A are claims; label them.

## CHANGELOG
- v0 (2026-11-04): first draft from the research plan, section 5.
- v0.1 (2026-11-05): added section 8 (open questions from the pilot build). No label definitions changed.
- v0.2 (2026-11-06): Jalal accepted all five section 8 proposals as rules (same as used by annotator A2/Codex).
- v1 (2026-11-07): after pilot round 1. Added MISREPRESENTED; NOT_ADDRESSED -> NOT_IN_SOURCE; A includes full decision texts; `inference` tag; decision order rule 1-4.
- v1.1 (2026-11-07, after round 2): a simplification copied from A's own press release is SUPPORTED (cause = copied). Frozen for the main study.
- v1.2 (2026-11-09, frozen, after calibration R1/R2, kappa 0.82): text parts and headline rule (3a); clarifications on copied simplifications, bundled claims and facts A does not state; fixed claim split in the main study; minutes per pair; human labels must be the annotator's own. Distortion_type field for MISREPRESENTED claims (the five prereg types). No label definition or decision step changed. Changes beyond the headline rule: prereg deviation D2. The dev-set (pilot) labels are not re-adjudicated under v1.2; they are used only for prompt development. Checked by Codex and a Claude agent (checks/guide12*.md).
