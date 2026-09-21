# VERDICT: blind assessment of A, B, C

Scope: fidelity to the seven captured pages in `./inputs/` only. Citations are `page:line`
(`01` home, `02` showcase, `03` tennis-agent, `04` domains, `05` local-models, `06` bt-inc-platform,
`07` reflect-shelf). I did not open `KEY.txt` or `runs/`.

---

## 1. Unsupported claims

### A

| # | Offending line | Purports to rest on | What the page actually says |
|---|---|---|---|
| A1 | "a SQLite unified database, six merged sensor sources" (A:11) | 03 | 03:150-152 says "SQLite Unified / 6 databases merged". The headline says "5 sensors" (03:31). The data-source line names five (03:43), and sensor support lists six (03:134-144). No page says "six merged sensor sources". A swaps a database count in for a sensor count. |
| A2 | "It also describes variation-specific tool bundles, local SQLite services, refresh pipelines, and Safe Mode snapshots." (A:13, where "It" is ShowcaseAgent or "the surrounding catalog") | 02 / 04 | Neither page mentions SQLite services, refresh pipelines or Safe Mode. Those terms appear only in the synthetic BT Inc manual (06). This is a misattribution: A takes properties of a fictional repository and gives them to the public catalog. The catalog category "simulation" in the same sentence is also not on 04 (its sections are Personal & Lifestyle, Enterprise & Industry, Research & Architecture). |
| A3 | "The TennisAgent discrepancy—189 on its own page versus 192 on the Reflect shelf" (A:37; also A:23 "calls the related `tennis-sensor-toolkit`") | 07 | The shelf gives 192 to `tennis-sensor-toolkit` (07:33-38) and lists **TennisAgent as a separate entry** with no tool count (07:61-67). Nothing makes them the same thing. A turns the word "related" into a count discrepancy for TennisAgent. |
| A4 | "Its most specific reviewed account says the runtime is desk-first, the shared shell/router is unverified" (A:43), used to rebut a misreading about *Bulkhead Tau* | 06 | 06 reviews `bt-inc-platform`, which 06:20-25 calls "a synthetic multi-domain conglomerate … not … evidence that a real operating company or unified production cockpit exists." It says nothing about Bulkhead Tau's runtime or ShowcaseAgent's router. A:31 makes the same move ("while the reviewed `bt-inc-platform` manual says the shared shell/router was not verified") as though the manual spoke to ShowcaseAgent. A:39 lists the synthetic OSAT desk's reviewer-identity gap as something "you cannot determine" about the real system. This is a scope error, and it is the most consequential error in A. |
| A5 | "The intended control flow is therefore: a request is bounded by a formal specification, routed through deterministic domain machinery, and recorded with evidence and verification." (A:7) | 01 | 01 describes boundaries ("bounding execution between a formal specification Charter above and an append-only evidence Logbook below", 01:56), not a per-request flow. A's "therefore" builds a request pipeline the page does not describe. Minor, but it is an invented mechanism. |

### B

| # | Offending line | Purports to rest on | What the page actually says |
|---|---|---|---|
| B1 | "a unified SQLite database that merges six sensor data sources" (B:9) | 03 | Same error as A1. The page says "6 databases merged" and gives the sensor count inconsistently (5 in one place, 6 in another). |
| B2 | "Whether TennisAgent has 189 or 192 tools. Its own page says '189 tools,' while Reflect calls `tennis-sensor-toolkit` a … '192 tools.'" (B:33) | 07 | Softer than A3 because B adds "These might be different repositories". Still, it frames a non-contradiction as an open question about TennisAgent when the shelf lists TennisAgent separately (07:61-67). The real TennisAgent discrepancy, 171 on 02:108/02:124, is absent. |
| B3 | "terminal escape sequences corrupted multiline JSON" (B:21) | 05 | 05:60 says "terminal sequences". "Escape" is a small technical embellishment and has no weight. Listed for completeness. |
| B4 | "supplies runnable local checks" (B:15) | 06 | 06:37-39 lists three commands. That they run is not shown. The page offers them as "Useful local checks", so "runnable" is the author's word. Minor. |

B has no mechanism taken from the synthetic manual and applied to the real system. B explicitly separates the two at B:29 ("the manual concerns a synthetic repository").

### C

| # | Offending line | Purports to rest on | What the page actually says |
|---|---|---|---|
| C1 | "a plan-then-execute engine over six merged SQLite databases containing watch, racquet, and fitness data" (C:7) | 03 | 03:150-152 says six databases were merged *into* "SQLite Unified". It does not say the six were SQLite, and "containing watch, racquet, and fitness data" is inferred from the sensor list. Minor overspecification, but closer to the page than A1/B1. |
| C2 | "That universal gating claim conflicts with the home page's unwired downstream gate; no distinction between separate enforcement mechanisms resolves it here." (C:17) | 01 / 04 | Overstated. 01 does separate the mechanisms: the "not yet wired" sentence sits inside the **Logbook** paragraph (01:78), while "gated by its own charter" (04:24) invokes the **Charter**, whose enforcement status 01 never states. The tension is real, since 01:88 also gives gating authority to the Engine Room, but "no distinction … resolves it" is wrong. The page draws the distinction and just doesn't say whether the Charter-side gate is wired. |
| C3 | "That describes a review method and its scope." (C:9), on the list of inspected components | 06 | Listing *what* was inspected (06:1105-1107) is scope, not method: it doesn't say whether the code was read, executed or tested. C partly undoes this in the next sentences ("'Verified live shape' is not itself a runtime demonstration"). |

C's numbers all check against the pages: 171/189, 38/41, 83/103, "Three of sixty-six costs 27.6%", 33/42/53/60, and the quoted "verifies that the file was written by reading it back" (06:1777-1778). I found no invented mechanisms.

**Section 1 tally:** A has five items, two of them substantive scope or attribution errors (A2, A4). B has four items, one substantive (B1). C has three, none of which imports facts from one page into another.

---

## 2. Accuracy of the demonstrated/asserted split

**Called evidenced, but the pages only assert it**

- **B:17**: "It also supplies an important negative result with its basis … This is not merely a caption containing 'verified'; the manual explains the review boundary." The "basis" is the manual's own list of reviewed and not-reviewed items. The same manual grades itself: "The generated manual passes the primary honesty check" (06:27) and "Synthetic/fiction boundary verified" (06:430). No procedure is described. B:15 also accepts "the page says they derive from reviewed repository/runtime evidence" without noticing that every chapter footer lists "Not reviewed: External runtime and integrations, Unreviewed runtime" (e.g. 06:539-540), and that 06:1111 excludes "Live databases, snapshots, or runtime state outside the reviewed code." The "runtime" in "reviewed runtime" is asserted, and the page's own boundary notes undercut it. B gives it more credit than the page earns. **C catches this** (C:9). **A misses it**: "'verified' in this manual means verified in the reviewed repository/runtime context described by the page" (A:21) repeats the page's framing.
- **A:21**: A presents "corrupt or non-list score history becomes blocked" as settled "method-level detail". The same page contradicts it at 06:1825-1833 (see §3). A treats a claim the page itself disputes as if it were evidence.
- **C:7**: "Portfolio tiers export 33, 42, 53, and 60 tools" is stated flatly as mechanism. The portfolio evidence boundary says only "the variation 1 and variation 4 tool registries" were reviewed (06:2405-2406), so 42 and 53 rest on the variations README, not on registries. A (A:19, "reports … portfolio tiers") is more careful here.

**Called asserted, but the pages actually evidence it**

- **Showcase "649+" tools.** The 14-row table (02:118-191) sums to exactly 649 (171+84+70+38+32+31+21+21+19+18+18+15+18+93). That internal arithmetic supports the headline figure. None of the three noticed. A:13 and A:43 treat "649+" as advertising copy, B doesn't address it, and C doesn't mention it.
- **80.6%.** C:13 correctly notes "The fraction supports the displayed percentage arithmetically" (83/103 = 80.58%). This is the one place an analyst credits in-page evidence that holds up. A:23 and B:19 lump it in with pure assertion without acknowledging the arithmetic. They are right that the method is missing, but they miss that the page does include a per-domain breakdown (02:118-191) in which **4 of 14 domains have no routing score** ("-"). So the 80.6% covers at most 10 domains, which none of the three says.
- **Local Models "passes all six probes."** C:15 correctly says the page describes the intervention (subprocess capture replaced by REST, 05:60), a partial method. B:21 says the page "explains a causal diagnosis" but then puts it with the unevidenced claims. Both are defensible. C draws the line more precisely.

**Net:** C's split is the most accurate and the only one that questions the manual's own "verified/runtime" vocabulary. B's split is sound on Showcase and Local Models but over-credits the manual. A's split is reasonable on headline numbers but accepts the manual at its word, including a claim the manual contradicts.

---

## 3. Cross-page (and intra-page) contradictions in the corpus

| # | Contradiction | Quotes | A | B | C |
|---|---|---|---|---|---|
| 1 | Logbook gate unwired vs. actively gating | 01:78 "Downstream execution gating is specified but not yet wired … an exit code that no caller currently enforces" vs 01:90 "actively gating execution" and 01:88 "gating execution authority" | Found | Found (quotes both, including 01:88) | Found |
| 2 | TennisAgent tool count | 02:108/124 "TennisAgent (171 tools)" vs 03:22 and 04:62 "189 tools" | **Missed** | **Missed** | Found |
| 3 | WQ tool count | 02:111/139 "WQ (38 tools)" vs 04:136 "41 tools across 7 projects" | Missed | Missed | Found |
| 4 | OSAT corrupt score history, within 06 | 06:57-58 "now fails closed when the JSON file is corrupt or not a list" (also 06:641, 06:698, 06:2440) vs 06:1830-1833 "When the score log is missing or unreadable, the desk falls back to an empty score state, and later hypotheses remain open instead of being blocked" | Missed (and repeats the first side as fact) | Missed | Found |
| 5 | Deterministic runtime vs. LLM routing | 01:58 "Rather than relying on non-deterministic language models for runtime control" and 01:70 "not an LLM talking to a simulated user" vs 02:59 "LLM fallback for ambiguous queries" and 02:93 "LLM makes one decision: 'which domain?'" | Not raised as a tension | Partly (B:31, determinism "may apply to selected routing") | Found (C:5) |
| 6 | Charter gating per domain vs. unwired gate | 04:24 "gated by its own charter" vs 01:78 | Cited only in the misreading | Missed | Found, but overstated (see C2) |
| 7 | "Verified live/runtime" vs. runtime not reviewed, within 06 | 06:337 "Verified live shape" and 06:93 "live runtime evidence" vs 06:1111 "Not reviewed … Live databases, snapshots, or runtime state outside the reviewed code" and 06:43 "Large SQLite databases are intentionally excluded" | Missed | Missed | Found (C:9) |
| 8 | Showcase adapter count, within 02 | 02:65 "14 uniform adapters" vs 02:202-206 Sprint 1 "TennisAgent adapter" + Sprint 2 "10 domain adapters", all "Complete" | Missed | Missed | Missed |
| 9 | TennisAgent sensor and tool arithmetic, within 03 | 03:31 "5 sensors" vs six listed at 03:134-144. The categories (03:78-88) sum to 150, or 155 with 5 smart tools (03:126), not 189 | Missed (A:23 cites "five sensors" and "detailed category counts" without checking them) | Missed | Missed |
| 10 | "14 production domains" vs. how the catalog labels them | 02:37 / 04:162 "14 production domains" vs 04:82 Stan "coursework domain", 04:136-140 WQ/AI_WQ "curriculum" | Missed | Missed | Missed |
| 11 | Semiconductors tiering, within 06 (minor) | 06:430 contrasts "Semiconductors changes by variation, portfolio grows by accumulation" vs 06:1268 semiconductors "The consequence is cumulative growth". Also "eight variation families" (06:1374) against six named tiers (06:1280-1300) | Missed | Missed | Missed |

**Not a contradiction, though two analysts treat it as one:** 189 (TennisAgent) vs 192 (`tennis-sensor-toolkit`). The shelf lists them as different entries (07:33-38, 07:61-67). C alone gets this right (C:19).

**Not a contradiction, correctly handled by B and C:** ShowcaseAgent's "unified interface" (02:43) vs BT Inc's unverified shared router (06:94). They describe different repositories. B:29 and C:27 say so. A:31 sets them against each other as though they bore on the same system.

C found 6 of the 7 real contradictions any analyst caught. A and B each found 1 cleanly. All three missed #8 to #11.

---

## 4. The likeliest misreading

All three name essentially the same misreading: **Bulkhead Tau currently enforces evidence-gated execution end to end.**

- **Invited or manufactured?** Genuinely invited. The quoted phrases are real and verbatim: "actively gating execution" (01:90), "gating execution authority" (01:88), "gated by its own charter" (04:24), "14 production domains" (02:37), and the page title "Deterministic Governance Substrate" (01:4). None of the three manufactured its supporting text.
- **A** widens it to "a single, production-ready governed platform in which every domain sits behind one deterministic router". The router half is invited by "unified interface to 649+ tools" (02:43). But A's rebuttal rests on the synthetic BT Inc manual ("Its most specific reviewed account says the runtime is desk-first", A:43), which says nothing about Bulkhead Tau's router. A's correction of the misreading is itself an instance of a different misreading (see below).
- **B** is the tightest statement and rebuts it only with 01:78, which is the correct and sufficient source.
- **C** is equivalent to B, adds the Domains quote, and rebuts correctly.

**Is it the strongest available?** No. The gating contradiction sits two paragraphs apart on a single page (01:78 vs 01:90), so any careful reader of 01 trips over it. A stronger misreading, which none of the three names, is:

> **Reading the synthetic BT Inc manual's "verified" findings as evidence about Bulkhead Tau's real domains.**

The corpus actively invites it:

- The manual is by far the largest and most evidence-shaped page (06 is 112 KB of the corpus's 135 KB, about 84%). It is hosted under the Bulkhead Tau path (06:1 `bulkheadtau.com/bulkhead-tau/reflect/…`) and repeatedly says "verified", "proved" and "What This Snapshot Proves".
- Its desks share names with real catalog entries: OSAT/AMKR (06:1580-1586) vs "Amkor Technology … OSAT" and "xamkor … OSAT advisory prototype" (04:86-92); Semiconductors (06:1127) vs Semiconductors (04:106); Portfolio (06:2015) vs Portfolio (04:142, 02:133).
- It shares code with the real system: "now loads the local BT Inc. OSAT tool module by file path rather than accidentally importing Project Phoenix's external `domains.xAmkor` copy" (06:68-71). The Reflect shelf footer reads "Project Phoenix // Bulkhead τ Release Line 2026" (07:71).
- Its own disclaimer is the only thing standing against the conflation: "should be read as a truthful map of a synthetic platform, not as evidence that a real operating company or unified production cockpit exists" (06:23-25).

A reader looking for the "demonstrated" part of the corpus will find almost all of it here and carry it over to the real system. A does exactly that: it uses the synthetic manual to settle questions about ShowcaseAgent's router (A:31), reviewer authority (A:39) and "the runtime" (A:43). That an analyst fell into it is the best evidence that it is the likeliest misreading. B (B:29) and C (C:9, C:27) avoid the trap but don't name it as the headline misreading.

A secondary candidate none of them names: treating the manual's "verified" labels as independent verification. The manual is generated by Reflect and certifies itself ("The generated manual passes the primary honesty check", 06:27; "Synthetic/fiction boundary verified", 06:430). The brief warned about exactly this.

---

## 5. Ranking

**1. C.** It has the most real contradictions found (six, including the three numeric and intra-manual ones both others missed). It is the only analyst to read the 189/192 pair correctly, the only one to question the manual's "live/runtime" vocabulary against its own not-reviewed lists, and the only one to credit in-page arithmetic (83/103). It imports nothing from the synthetic repository. Weaknesses: it overstates the Domains-vs-home gating conflict (C2), calls a scope list a "method" (C3), writes unsectioned prose that makes the four requested parts harder to find, and misses the adapter, sensor and category arithmetic.

**2. B.** Mechanically accurate, best structured, and correct to keep the synthetic manual scoped (B:29). Its misreading statement is the cleanest. It quotes both sides of the one contradiction it finds, including 01:88. Weaknesses: "six sensor data sources" (B1). It frames 192 as a TennisAgent question (B2) and misses the real 171 figure. It misses the intra-manual corrupt-history contradiction, the WQ count and the runtime-vocabulary tension. It also over-credits the manual's self-reported "basis" (B:17).

**3. A.** A competent summary that fails on the thing the brief cared most about. It attributes BT Inc-only properties (SQLite services, refresh pipelines, Safe Mode) to the public catalog or ShowcaseAgent (A2). It states the 189/192 non-discrepancy flatly as "The TennisAgent discrepancy" (A3). It uses the synthetic repository's findings to answer questions about Bulkhead Tau itself, in its cannot-determine list and in its misreading rebuttal (A4). It repeats a claim the manual contradicts as settled detail. It finds only the one contradiction everyone found.

**Confidence:** C over B, about 70%. B is cleaner, but C's extra contradictions are real and verified against the pages, and C's errors are overstatements rather than inventions. B over A, about 85%. A's scope conflation is a fidelity failure of the kind section 1 exists to catch, and B avoids it explicitly.
