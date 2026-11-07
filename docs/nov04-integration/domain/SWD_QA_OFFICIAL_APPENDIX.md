# SWD / Hong Kong Official Appendix — Licence-Specific Staffing Rules for Emma

**As-of date:** 1 November 2026  
**Prepared by:** Manus AI  
**Purpose:** implementation guardrails for workflow and compliance Q&A; not independent legal certification.

## Q1. May Emma treat elderly homes as “high / medium / low care” facilities?

No. The two licensing regimes use different facility classifications and must be kept separate.

For **residential care homes for the elderly (RCHEs)**, the official types are *nursing home*, *care and attention home*, *aged home*, and *self-care hostel*. A nursing home is for residents requiring a high degree of professional nursing care, whereas a care and attention home is for residents who need personal care and attention but not that high degree of professional medical or nursing care. The elderly-persons Code says nursing homes are governed by the separate Nursing Homes Code. [1] [3]

For **residential care homes for persons with disabilities (RCHDs)**, the official types are *high care level*, *medium care level*, and *low care level*. The RCHD Code defines them by the residents’ care and assistance needs. In a mixed RCHD, low-care residents are disregarded for this classification: the home is classified as high or medium; it is high where at least 30% of the combined medium- and high-care places require high-care service, otherwise medium. [2]

**App rule:** never map an RCHE’s care-and-attention / aged / self-care terminology to an RCHD high / medium / low label, or vice versa. Do not state or infer a particular facility’s class without its current licence or other authoritative licence record. Until confirmed, show **“licence classification not confirmed — statutory rule calculation unavailable”**, rather than selecting a rule set.

## Q2. Which statutory rule set should the app select and cite?

Select by the **licence regime and licence type**, not by a local label, resident mix shorthand, team name, or a staffing target:

1. Confirm the facility’s regulatory family: **Cap. 459A** for an RCHE or **Cap. 613A** for an RCHD.
2. Confirm the licence type/class. For an RCHE nursing home, route to its distinct nursing-home code/rule set; do not apply the non-nursing RCHE tables below. For a mixed RCHE or RCHD, persist the regulator-recognised home type/class, not a calculated resident-level surrogate. [1] [2] [3]
3. Select the version whose effective interval contains the assessment date. Store the legal citation down to **Regulation → Schedule 1 → applicable table/item**, plus the SWD Code paragraph/page used for explanatory text. Store `effective_from`, `effective_to` where superseded, source URL, retrieval date, and any DSW-approved “specific hours” version.
4. Evaluate each rule against resident count and actual time coverage. The Codes say resident counts are rounded up to the next applicable multiple. This is not an aggregate monthly-hours test. [3] [4]

A sensible immutable result record is: `facility_id; licence_evidence_id; regime; licence_class; rule_version; assessment_date; Schedule_1_table_item; required_role_category; resident_count_and_rounding; approved_specific_hours_id; actual_on_duty_coverage; outcome; source_URL; source_section_page`.

## Q3. What phase-in text was verified in the Codes, and what still needs current-law verification?

The accessible 2024 Codes are not, alone, the complete current source for an assessment after 14 October 2026. The official 5 June 2026 announcement describes introducing nursing-care practitioners as permitted staffing alternatives under the relevant rules, while retaining the existing staffing requirements, and changing nursing-home calculation from beds to resident numbers. It stated implementation on 14 October subject to completion of legislation. The latest enacted Schedule 1 must determine exact permitted roles/items; do not silently equate nursing-care practitioner with RN or count the same person twice. Current e-Legislation pages were followed but their complete client-rendered text was unavailable in this extraction. Accordingly the Code example below illustrates the older nurse/health-worker pathway, not an exhaustive statement of all current alternatives or a licence-specific certification. [5]

The 2023 amendments were phased for staffing. For both a **care-and-attention RCHE** and a **high-care RCHD**, the SWD Codes state that from **16 June 2026** the nurse/health-worker requirement is **13 hours within the specified period each day**: one nurse for every 60 residents **or** one health worker for every 30 residents. From **16 June 2028**, a home in either of those classes with more than 60 residents also needs at least one nurse and one health worker for 8 hours within the specified period, in addition to the preceding requirement. For RCHEs, the cited text requires the nurse or health worker to be **on-site and on duty**; the RCHD high-care table says **on duty** and separately requires one staff member on-site and on duty whenever a resident is present. [1] [2] [3] [4]

**Example only — not a facility classification or complete compliance conclusion:** for a confirmed high-care RCHD with 31 residents assessed on or after 16 June 2026, the Table 1 rounding instruction takes 31 to 60. The nurse/health-worker component is therefore one nurse, or two health workers, on duty for the required 13 hours. Other independently applicable Table 1 rows, including care-worker, ancillary-worker, night and continuous-presence requirements, must still be tested. [2]

Do not present the 16 June 2028 addition as already in force on the as-of date. The official statutory schedule remains the controlling text; the SWD Codes provide the readable implementation text and the stated phase-in dates. [1] [2] [3] [4]

## Q4. How should staff roles map in the product?

Use a controlled regulatory-category field, separate from payroll job title. Under the cited older Codes:

- **Nurse:** a person on the register of nurses or roll of enrolled nurses under the Nurses Registration Ordinance.
- **Health worker:** a person responsible for health and care services to residents; the RCHD Code also states that operators must not employ a person as a health worker unless registered.
- **Care worker:** a person employed to render personal care, other than an ancillary worker, health worker, or nurse.
- **Ancillary worker:** a person other than those three categories whose duties include, for example, cook, domestic servant, driver, gardener, watchman, welfare worker, or clerk.

This is a regulatory-role mapping, not a title-matching exercise. One person must be counted only in the role/category and substitution mechanism the applicable Schedule item permits. A role’s inclusion in a payroll title, or performing a task sometimes associated with another role, is not evidence that the statutory category or registration condition is met. [3] [4]

## Q5. How should Emma distinguish the statutory floor, stricter operating minima, and paid hours?

The **statutory floor** is the minimum presence/category requirement from the licence-specific Schedule 1 item, including its time window, rounding, on-duty/on-site wording, and any approved specific hours. For non-nursing RCHEs and RCHDs, “specific hours” are periods within 6 a.m.–10 p.m. which total the required hours and are approved by the Director of Social Welfare; proposed changes require approval before implementation. [3] [4]

A provider’s **organisation, service, shift, or task minimum** may be stricter. Model it as a separately versioned policy layer with its owner, scope, effective date, approval, and source. Label it `organisation/task minimum`, not `statutory minimum`. In particular, **do not assume that SA operational staffing minima are statutory, and do not import them to NAAC** without an explicit, licence-specific policy decision and source.

**Actual on-duty coverage** is a time-based presence test. Paid hours, contracted hours, planned roster hours, headcount, and FTE are different measures. The Codes require compliance at the relevant times and call for appropriate relief where leave would otherwise prevent compliance. Therefore, paid-hour totals may support operations analytics but must not by themselves produce a statutory-pass result. Capture both planned and actual attendance/status, with exceptions and corrections audited. [3] [4]

## Q6. What should the Q&A say when data are missing or the question asks for certification?

Use bounded answers: “The applicable statutory rule cannot be selected until the current licence regime and class are confirmed.” Cite the candidate legislation and Code, state the assessment date, and list the missing evidence (licence type/class, resident count, approved specific hours, eligible role/registration, and actual on-duty attendance). Do not answer “compliant”, “non-compliant”, or certify a facility from a source extract or planned roster alone. Escalate a contested or consequential interpretation to the operator’s responsible person and suitably qualified Hong Kong legal/compliance adviser.

**Data boundary:** do not send source history, actual roster data, personnel data, resident data, or licence evidence to an external LLM prompt. If an LLM is used at all, give it a pre-approved, non-sensitive rule excerpt and require it to return the stored citation/version rather than inventing a legal conclusion.

## References

[1]: https://www.elegislation.gov.hk/hk/cap459A!en "Residential Care Homes Elderly Persons Regulation Cap 459A"

[2]: https://www.elegislation.gov.hk/hk/cap613A!en "Residential Care Homes Persons with Disabilities Regulation Cap 613A"

[3]: https://www.swd.gov.hk/storage/asset/section/417/Code_of_Practice_for_Residential_Care_Homes_for_the_Elderly_June_2024_Revised_Edition%282%29.pdf "SWD Code of Practice for Residential Care Homes Elderly Persons June 2024 Revised Edition"

[4]: https://www.swd.gov.hk/storage/asset/section/423/Code_of_Practice_for_RCHDs_June_2024_Revised_Edition_Eng_%28Updated%20in%20Oct%202024%29.pdf "SWD Code of Practice for Residential Care Homes Persons with Disabilities June 2024 Revised Edition"

[5]: https://www.info.gov.hk/gia/general/202606/05/P2026060500319.htm "Hong Kong Government 2026 care-home amendments and nursing-care practitioner announcement"
