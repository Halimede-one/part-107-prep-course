# Sources: authoritative references

All course content is grounded in and cited to the official material below. When a lesson or question turns on a precise regulatory fact, the ground-truth answer comes from these sources, not from model recall. This is the source list that the grounding boundary (facts plus readiness gate) relies on, and the knowledge base in `knowledge-base/regulations/` is built from it: `knowledge-base/sources.json` names each document, where it is fetched from, and how it is cut into chunks.

## Governing standard

The exam blueprint. Every ACS code the course is built around comes from this document.

- **FAA-S-ACS-10B, Remote Pilot - Small Unmanned Aircraft Systems, Airman Certification Standards.** Effective April 6, 2021; current in October 2026 (no later revision is published). Supersedes FAA-S-ACS-10A.
  - Verified location: https://www.faa.gov/training_testing/testing/acs/uas_acs.pdf

## Primary regulatory sources (ground truth for precise facts)

The law itself. For altitude ceilings, speed and visibility limits, registration thresholds, waiver rules, and any other precise regulatory fact, the CFR is authoritative. The guidance below explains the law but does not override it.

- **14 CFR part 107**, Small Unmanned Aircraft Systems (sUAS). The core operating rule.
- **14 CFR part 89**, Remote Identification (RID).
- **14 CFR part 48**, Registration and Marking Requirements for Small Unmanned Aircraft.
- **14 CFR part 47**, Aircraft Registration.
- **14 CFR part 3, subpart D**, Falsification, Reproduction, Alteration, Omission, or Incorrect Statements. Since November 3, 2025 this subpart holds the falsification rule for every part of Title 14; 107.5 and 89.5 are reserved.
- **14 CFR part 1**, Definitions and Abbreviations. Part 107 definitions control where they conflict, but terms such as "night" come from 1.1.
- **14 CFR 61.56, 91.17, 91.19, 91.137 to 91.145, and 99.7**, the sections that part 107 incorporates by reference (flight review, alcohol and drugs, temporary flight restrictions, special security instructions).
- **49 U.S.C. 44809**, Exception for limited recreational operations of unmanned aircraft. The statute that 107.1 excludes from part 107.
- Authoritative host for the CFR: the Electronic Code of Federal Regulations at ecfr.gov, current edition. The knowledge base prints the current eCFR text at build time; the annual edition on govinfo.gov lags it by up to a year. The statute comes from the U.S. Code on govinfo.gov.

## FAA guidance and handbooks (explanatory)

Plain-language explanation and worked context. Good for teaching, cited alongside the CFR rather than in place of it.

- **AC 107-2A**, Small Unmanned Aircraft System (Small UAS), February 1, 2021. Current; AC 107-2 is cancelled.
- **FAA-G-8082-22**, Remote Pilot - Small Unmanned Aircraft Systems Study Guide, 2016. Still the edition the ACS references.
- **FAA-H-8083-25C**, Pilot's Handbook of Aeronautical Knowledge: Chapter 14 (Airport Operations), Chapter 15 (Airspace), and Chapter 17 (Aeromedical Factors). The chapters the Regulations area draws on; other chapters join when their areas are built.
- **Aeronautical Information Manual (AIM)**: Chapter 3 (Airspace, sections 1 to 5) and Chapter 11 (Unmanned Aircraft Systems, sections 1 to 8), as published in HTML on faa.gov.
- **FAA Unmanned Aircraft General (UAG) sample questions**, August 10, 2021. Official examples of exam items, keyed to ACS codes. No answer key is published, so they illustrate the exam's style and never key an answer.
- **FAA web guidance at faa.gov/uas**: Operations Over People General Overview, Remote Identification, Part 107 Waivers, LAANC, Airspace Restrictions, Airspace 101, Where Can I Fly, How to Register Your Drone, Become a Certificated Remote Pilot, B4UFLY, and Recreational Flyers. Web pages change without notice; `knowledge-base/pdfs/fetch-log.json` records when each was read.
- Host: faa.gov (use the current edition of each).

## Rulemaking preambles (explanatory, dated)

The Federal Register final rules explain why each provision reads as it does. They are dated documents: a statement in a preamble describes the rule as adopted in 2021, and a later amendment can overtake it.

- **86 FR 4314**, January 15, 2021: Operation of Small Unmanned Aircraft Systems Over People (the categories, night operations, recurrent training).
- **86 FR 4390**, January 15, 2021: Remote Identification of Unmanned Aircraft.

## Precedence rule

1. The statute and the CFR (49 U.S.C. 44809; 14 CFR parts 1, 3, 47, 48, 89, 107, and the referenced sections of parts 61, 91, and 99) are the ground truth for any precise regulatory fact.
2. FAA-S-ACS-10B defines what is testable and how it is coded. It is a map, not an answer source.
3. FAA guidance (AC 107-2A, FAA-G-8082-22, FAA-H-8083-25C, the AIM, the sample questions, and the faa.gov pages) provides explanation and context.
4. The Federal Register preambles provide the reasoning behind a rule, as of the date of the rule.

If a lower source and the CFR ever appear to conflict, the CFR wins and the discrepancy is flagged for review rather than resolved by the model.

## Reference mapping for the Regulations area

The ACS lists specific references per task. Content and reference-fact entries for each task should cite from that task's set.

| Task | ACS references |
|---|---|
| I.A General | 14 CFR parts 89 and 107 subpart A; AC 107-2; FAA-H-8083-25; FAA-G-8082-22 |
| I.B Operating Rules | 14 CFR parts 47, 48, 89, and 107 subpart B; AC 107-2; FAA-H-8083-25; FAA-G-8082-22 |
| I.C Remote Pilot Certification | 14 CFR part 107 subpart C; AC 107-2; FAA-H-8083-25; FAA-G-8082-22 |
| I.D Waivers | 14 CFR part 107 subpart D; AC 107-2; FAA-H-8083-25; FAA-G-8082-22 |
| I.E Operations Over People | 14 CFR parts 89 and 107; AC 107-2; FAA-H-8083-25; FAA-G-8082-22 |
| I.F Remote Identification (RID) | 14 CFR part 89; AC 107-2; FAA-H-8083-25; FAA-G-8082-22 |

Note: the ACS was written before the 2025 falsification rule. The falsification element of Task A (UA.I.A.K3) now cites 14 CFR 3.401 to 3.405 rather than 107.5.

## Currency notes

- FAA-S-ACS-10B is the current standard in October 2026.
- 14 CFR 107.5 and 89.5 were removed and reserved on November 3, 2025 (90 FR 42517, September 3, 2025). The falsification, reproduction, alteration, and incorrect-statement rules for all of Title 14 now live in 14 CFR part 3, subpart D.
- 14 CFR 107.1(b) no longer names part 101; the recreational exclusion is "any aircraft subject to the provisions of 49 U.S.C. 44809" (amended 2021).
- Part 108 (a separate framework for routine beyond visual line of sight operations) was still under final review in October 2026. It is not part of the Part 107 knowledge test as tested today and is out of scope for this course.
- The full reference list for the other four Areas of Operation (including the weather and lithium-battery SAFOs) is in Appendix 4 of FAA-S-ACS-10B and will be brought in when those areas are built.
- Use the current edition of every document above; verify against the official host before finalizing any precise fact. Re-run `tools/fetch_sources.py --redo` and `tools/build_kb.py` to refresh the knowledge base from the current eCFR text.
