# VERDICT: blind assessment of A, B, C

Task: operator-describe-20260921. Scope: fidelity to the six captured pages in `inputs/`, nothing else.
Line references are to the captured files: `01` README, `02` Operator Shell page, `03` owner's manual,
`04` Grok paper, `05` board, `06` Graphify page.

---

## 1. Unsupported claims

### A

A is the cleanest of the three. I found no invented mechanisms and no numbers that are not on the page.
Every figure it gives (nine domains, 41/41, 39/41, 183/449, 3.1x, 216 cells, 15/10/11-of-32, 97 turns)
appears in the source. Its problems are small:

1. **Acronym expansion.** "evidence content-addressed storage" (A para 4). The corpus only says
   "evidence CAS" (`01:92`). "content-addressed" appears in none of the six documents. The expansion is
   plausible, but it reads a capability into an acronym. Minor.
2. **Misattribution to the manual.** "The [manual] additionally describes ... Its optional authority
   architecture adds a separate broker, external store, evidence content-addressed storage, receipts,
   reconciliation, and root-managed administration." "External store" and "evidence CAS" come from the
   README (`01:92`), not the manual. The manual says "authority store" and never mentions CAS. Minor.
3. **Treating paper-internal quotes as support.** "The quoted correction and Grok's response support the
   reported format-selection mistake." Those quotes (`04:90-116`) are excerpts the paper chose to show.
   Nothing in the packet lets a reader check them against a transcript. They illustrate the paper's
   account. They do not support it independently. (Also counted under §2.)

### B

1. **"reproducible worked example ... demonstrates two expected failures ... It also provides the
   commands"** (B §2). This purports to rest on `01:185-228`. The page links `examples/verified-work/run.sh`
   but does not include it. The commands the page *does* show (`01:199-228`) are "written out for reading
   rather than running". They run in default `single_user` mode, never edit evidence after attachment, and
   never try an enforced-mode self-verification. Neither failure case B describes appears in the displayed
   commands. B does hedge ("if the described CI execution is accurate"), but "reproducible", "demonstrates"
   and "provides the commands" are still not supported.
2. **"The materials establish a UID check"** (B §3, bullet 2). The only place a same-UID refusal happens
   is the unshown `run.sh` (`01:193`). Everywhere else the UID rule is specification prose (`01:246-251`).
   The materials describe a UID check. They do not establish one.
3. **Graphify "gives no raw output"** (B §2). This overstates the gap. `06:538-562` shows a truncated
   `graphify explain "load_yaml()"` result with node, source line, degree and six tagged edges. The page
   gives partial raw output, not none.
4. **"a component of Phoenix/Bulkhead Tau"** (B §4). No page says or suggests that Operator is part of
   Project Phoenix. Phoenix appears only on the Shell page (`02`) and in one board next-action (`05:418`).
   B has merged the Bulkhead-τ framing from `04` with the unrelated Phoenix page. Minor.

### C

1. **"the page gives the script and commands needed to reproduce it"** (C §2). This is the most serious
   unsupported claim in any of the three answers. It purports to rest on `01:185-195` / `03:1250-1265`.
   Neither page gives the script. Both give only a link to it, and the snippet they do display contains
   neither failure scenario (see B.1). C also calls these "the observed checks", but the reader observes
   nothing. The checks are narrated.
2. **"The owner's manual likewise separates ordinary local work from enrolled authority ... Thus the parts
   fit as a local ledger first, with an unintegrated external authority path beside it"** (C §1). This
   rests on `03` but does not match it. The manual's chapters describe enrolled operation in the present
   tense, under "Verified Facts" headings: "If the repository is enrolled, ordinary commit requests are
   role-gated and the broker becomes the authority boundary" (`03:215-216`), "The client side resolves
   enrollment through a fixed registry and repository identity check" (`03:642-644`), and "Ordinary
   broker commits are builder- or verifier-gated" (`03:240`). Only the manual's hand-edited Configuration
   section (`03:1470-1472`) says it is unintegrated. "Likewise" makes a disagreement look like agreement.
3. **"'verified' establishes a recorded, identity-gated status under the ledger's rules"** (C §4). In the
   default mode this is wrong. `01:214` records `--status verified --verified-by reviewer` "in the default
   single_user mode". `01:331-332` says that in that mode "the builder can assert a reviewer's name".
   `01:23-24` says such verification is "explicitly advisory". A default-mode "verified" is gated by a
   name the builder types, not by identity. C's correction of the misreading is itself a misreading.
4. **"This demonstrates that a graphify analysis produced those numbers"** (C §2). This rests only on the
   page's own captions, "Real output ... Not a mockup" (`06:483`) and "Real numbers, not illustrative
   ones" (`06:564`). That is the same kind of caption-as-method that the analysts were told not to accept.
5. **"evidence content-addressed storage"** (C §1). Same acronym expansion as A.1.
6. **"it is a view of one project ledger"** (C §1). The board is a view of one task *prefix*
   (`01:71-81`, `05:273`), not of a project ledger. C's "The live board" (§2) uses the manual's label
   (`03:8`) for a page that calls itself a "snapshot 2026-09-16 23:19 UTC" (`05:275`). Minor.

---

## 2. Accuracy of the demonstrated/asserted split

The asymmetry that matters most here is the README worked example. The displayed code (`01:199-228`) is
evidence, by construction, of one thing: `--status verified` can be recorded against a log produced by
`printf 'ok\n'` (`01:205`), for a claim ("uploader retries 3x on 5xx", `01:212`) that the gate test does not
exercise. The test only checks `n <= 3` (`01:204`). The accompanying caption promises the opposite:
"attach verifiable evidence (with an explicit verification command and reviewer signature)" (`01:197`),
and a CI script that "cannot quietly stop working" (`01:188`).

| | Called demonstrated, but the page only asserts | Called asserted (or ignored), but the page evidences |
|---|---|---|
| **A** | The Grok correction exchange "supports" the reported miss (see A.3). Mild. A frames the Graphify output as "displayed measurement output with a named production pipeline", but then withholds the answer-quality inference, so this is borderline acceptable. | A gets this right. It is the only analyst that reads the displayed snippet as evidence *against* the caption: "This demonstrates the proposed command sequence and how an advisory status can be recorded, not a successful test run," and "no upload or HTTP failure is tested." It also correctly says the CI claim "supplies neither that script nor CI output here." It counts the board's counts as observable, which is correct: the per-card ratios in `05` sum to 11/32, and there are 15 cards, 10 marked verified and 3 marked STALE, so the headline figures check out internally. |
| **B** | "The strongest displayed product evidence is a reproducible worked example, not merely a success caption." The central claim here (`01:187-193`) *is* a success caption. The script and the CI log are both absent (see B.1). The conditional hedge limits the damage but does not fix the classification. "The materials establish a UID check" is the same error in a smaller form. | B misses the snippet's own evidence (the `printf 'ok'` log and the claim/test mismatch). It calls the Graphify page raw-output-free when part of the output is shown (B.3). The 3.1x figure is also arithmetically consistent with the displayed ~12,200 / ~3,901 token counts (`06:517-519`). The ratio is on the page. Only its inputs are asserted. |
| **C** | "The strongest demonstrated behavior is the local record workflow ... the page gives the script." This is wrong in both classification and fact (see C.1). "This demonstrates that a graphify analysis produced those numbers" accepts a caption as a method (C.4). | C misses the snippet's own evidence entirely. The one thing the displayed workflow actually demonstrates is that default-mode "verified" is self-asserted, and that is the opposite of how C uses it. |

On the Grok paper (`04`), all three treat "two independently verified git commits" correctly as reported
and not checkable here. A is the most exact: the paper *does* name a method ("cross-referencing the session
transcript ... against git log", `04:60`). That makes it more than a caption, and A says so. None of the
three notes that the verifier the paper implies is its own author (`04:18`, "Author: blue-az"), who is the
same human operator that git attributes Grok's commits to (`04:60`). "Independently" in `04` does not mean
a separate identity in the ledger's sense.

None of the three flags that the manual presents its findings under repeated **"Verified Facts"** headings
(`03:229, 361, 545, 683, 843, 1120`) while also saying it was "written from a static read of the source
tree" (`03:87`). That is exactly the "'verified' in a caption is not a described method" case the analysts
were warned about. A, B and C all note that the manual comes from a static read, but none connects that to
the heading.

---

## 3. Cross-page contradictions

Real contradictions in the corpus, by weight:

1. **Is the broker/enrollment path integrated?**
   - README: "Protected policy/service installation, CLI integration, and enrollment remain separate work"
     (`01:94-95`); "`operator` and existing `.operator` ledgers do not consult the external authority yet"
     (`01:273-274`).
   - Manual chapters: "If the repository is enrolled, ordinary commit requests are role-gated and the
     broker becomes the authority boundary" (`03:215-216`); "The client side resolves enrollment through a
     fixed registry and repository identity check" (`03:642-644`); "Verified Facts: Ordinary broker commits
     are builder- or verifier-gated" (`03:240`). The manual's own Configuration section repeats the README's
     "do not consult" line (`03:1470-1472`), so the manual also contradicts itself.
   - **A found it** and quotes both sides, including the manual's internal contradiction. **B quotes both
     sides** but explains the difference away as "designed/partly implemented", so it is found but
     softened. **C missed it** and describes the manual as agreeing ("likewise").

2. **Installed or not installed?**
   - README heading: "P3 broker component (not installed)" (`01:90`). Known limitations: "The standalone P3
     broker component is not yet installed or integrated" (`01:338-339`).
   - The same README: "The service is installed but not started or enabled" (`01:274`), repeated in the
     manual at `03:1472`.
   - **All three missed it.** B quotes "installed but not started" as fact. C quotes "not installed" as
     fact. Each took one side without noticing the other.

3. **Standalone product or part of Bulkhead τ?**
   - README: "a standalone, domain-neutral control plane ... Operator does not import, invoke, or require
     Bulkhead Tau" (`01:40-41`), repeated in the manual at `03:109-111`.
   - Grok paper: "registered as a peer harness inside Bulkhead τ's Operator system" (`04:22`); "Published
     as part of the Bulkhead τ release line" (`04:176`).
   - This is a disagreement in framing more than a technical one. **A found it** and correctly adds that
     "ownership phrasing does not establish a software dependency". **B found it** and quotes both sides.
     **C missed it.**

4. **Is harness support proven?**
   - Manual: "That each provider's CLI still behaves as this product expects is not shown here"
     (`03:93-94`); "does not prove a full support list" (`03:900-901`).
   - The same manual: "Harness support is proven only for cataloged profiles. The twelve profiles seeded at
     operator init are the validated set" (`03:1546-1548`); "whether the cataloged harness profiles are the
     supported set (they are)" (`03:1599-1600`).
   - Cross-page: the board reports that generated review delegations fail on credentials and PATH
     (POE-ISS-012) and that the cataloged Grok target resolved to the wrong provider (POE-ISS-014,
     `05:449-451`).
   - Also, the manual says the twelve profiles are "listed in the command reference" (`03:91-92`). The
     captured command reference lists four `usage-import` harnesses and six `delegate-brief` harnesses,
     not twelve profiles.
   - **A partly found it**, as a gap "between catalog entries and the board's failed review paths". **B and
     C quote only the "not shown" side.** None quotes "proven ... validated set".

5. **The headline promise versus the default mode (inside the README).**
   - Headline: "It enforces a narration-vs-execution partition: an agent's claim ... only counts once it
     has evidence attached and is verified by a different identity" (`01:12-15`).
   - Default mode: "default `single_user` verification still work[s] but [is] explicitly advisory"
     (`01:23-24`); "the builder can assert a reviewer's name" (`01:331-332`). The worked example uses
     exactly that path (`01:214-217`).
   - Lines 22-24 qualify the headline, so this is a qualified tension rather than a flat contradiction.
   - **A comes closest**: it says the snippet shows "how an advisory status can be recorded". **B** lists
     "enforces a narration-vs-execution partition" as an assertion but does not set it against the default.
     **C** repeats the headline's framing.

6. **Minor tensions, missed by all three:**
   - OpenCode status: the manual's local A/B tool compares "two local OpenCode arms" (`03:1033`, listed as
     "Confirmed here" at `03:1178`), while the README says OpenCode "is deprecated as the carrier"
     (`01:44`, `01:280-281`). The manual is scanned at a different pin (`03:72-74`), which may explain it.
   - "Live" versus "snapshot": the manual labels the board "live ledger orientation" (`03:8`); the board
     calls itself a snapshot (`05:275`).
   - Subcommand count: "23 subcommands" (`01:112`, `03:1305`) matches neither 22 (the plain CLI names
     listed) nor 24 (including `crystal-attach` / `crystal-import`).

**Tally.** A found #1 and #3 in full and #4 and #5 in part. B found #3, found #1 in a softened form, and
missed the rest. C found none.

---

## 4. The likeliest misreading

- **A: "Operator establishes whether completed work is true."** This is genuinely invited. The README's
  first line is "Do you actually know that's true?" (`01:8`), and A quotes "Is that true, and did a
  different identity check?" (`01:33-34`). A counters with the correct passage (`01:346-347`). It is not
  manufactured, and it is well grounded.
- **B: "Operator already provides a tamper-resistant, independently governed verification service."**
  This is genuinely invited, more by the manual than the README: `03:215-216`, `03:589-592`, and the
  "Verified Facts" at `03:240`. B's counter-quotes ("same writable disk", "not ... an adversarial
  tamper-proof boundary", "self-amendable", "still not repo CLI integration") are all accurate. It is
  well built. Its weakness is that the README disclaims this reading loudly and repeatedly, so a careful
  reader is less likely to fall into it.
- **C: "'verified' means the underlying software result was independently rerun and proved."** This is
  genuinely invited: "a different-identity sign-off" (`01:131`) and the board's "verified" badges. But
  C's own correction repeats a narrower form of the misreading (see C.3).

**A stronger misreading that all three missed as their headline:** *a "verified" label means a different
identity checked the work.* This goes one step before the semantic question that A and C raise. It is not
"was the check meaningful?" but "was there a second checker at all?"

- The README promises that a claim "only counts once ... verified by a different identity" (`01:13-15`),
  and its prose says the example attaches evidence "with ... reviewer signature" (`01:197`).
- The code under that prose is "record an advisory verification in the default single_user mode"
  (`01:214`), with `--verified-by reviewer` typed by the same user who wrote the claim and wrote `ok` into
  the log (`01:205`).
- The README's own limitation: "When every agent runs under one OS user, the builder can assert a
  reviewer's name" (`01:331-332`).
- The board then reports "10 verified tasks" (`05:279`) with no advisory/`uid_isolated` split. Its issues
  say the distinct-UID path "currently blocks on ad hoc sudo/auth state" (`05:444`) and that generated
  verifier delegations "are not yet reliable end-to-end" (`05:449`).

A reader who takes the board's "verified" in the sense of the README's headline will overcount
independent verification, and nothing in the packet lets them correct for it. A (unknown #2, "advisory
from isolated status") and B (§2, "distinct-UID verification") both raise this as an open question. C
asserts the opposite.

---

## 5. Ranking

**1. A.** A is the only answer that reads the worked example against its caption (`printf 'ok'`, and a
claim the test does not exercise). It is the only one to classify the CI claim correctly as unshown, and
the only one to quote both sides of the broker-integration contradiction, including the manual's internal
contradiction. It also catches the Bulkhead framing without over-reading it, and it has no invented
numbers. Its faults are minor: the CAS expansion and misattribution, and treating the Grok quotes as
support. It uses no section headers, but all four requested parts are present.

**2. B.** B is well organized. Its misreading is well evidenced and quoted on both sides, it catches the
Bulkhead disagreement, and its unknowns are specific. It is marked down for calling the unshown `run.sh`
"the strongest displayed product evidence" and "reproducible", for turning the broker disagreement into
"partly implemented" instead of naming it, for missing installed-versus-not-installed while quoting one
side, and for small overstatements ("no raw output", "establish a UID check").

**3. C.** C's prose is careful and its Shell-page and Graphify category separation is good. But it
contains the most consequential unsupported statement in the set: that the page "gives the script and
commands needed to reproduce" the failure cases. It finds no cross-page contradictions, which the
analysts were explicitly asked to quote, and it describes the manual as agreeing with the README where
they disagree. It accepts the Graphify caption as demonstration. Its final correction ("identity-gated
status") is wrong for the default mode that the corpus actually shows.

**Confidence.** A over B: moderate-high, about 75%. B's misreading section is arguably stronger than A's,
but A's split and contradiction work are clearly better. B over C: high, about 85%, on the strength of
C.1, C.2 and C having found no contradictions. The overall order A > B > C: about 70%.
