"""Rebuild outcome-blind manual annotations and strict signal manifests.

Run duration_buried_screen.py first. IDs below refer to its frozen, hashed input.
The web-reviewed main filings and relevant exhibits are recorded as links and
short factual paraphrases. No prices or subsequent filings are read here.
"""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT_SHA = '2811f3fffeb007df61b9756767aeb50762c86e84de615055dd2a5966b6920cab'

# Every screened filing receives a distinct economic exclusion explanation.
# A dates/quarters mention is not automatically an operational risk end date.
NOTES = '''
0|settlement_not_operating_duration|Proposed derivative settlement; hearing/approval is not the end of an ongoing operating disruption.
1|one_time_charge|Tax judgment creates a one-time charge in the quarter ending September 28; that accounting date is not risk resolution.
2|one_time_charge|Acquired IPRD and milestones expense is a financial charge, not a temporary operational failure.
3|one_time_charge|Emraclidine impairment follows failed clinical studies; no stated 60–180-day return to normal operations.
4|one_time_charge|Acquired IPRD expense affects quarterly EPS, without an operating disruption horizon.
5|settlement_not_operating_duration|Derivative litigation settlement; no temporary operational impairment with a bounded recovery period.
6|out_of_range_and_not_resolution|AT&T Mexico rent withholding is ongoing; August 2026 arbitration is over 180 days away and a hearing is not assured resolution.
7|no_explicit_risk_end|Partial rent settlement restores most payments; escrow release depends on arbitration or consent without a dated end.
8|transaction_not_operating_duration|Accertify sale/reclassification is a strategic disposition, not a dated temporary operating disruption.
9|settlement_not_operating_duration|Marketing/sales investigation settlement does not state a temporary operating recovery horizon.
10|settlement_not_operating_duration|Deferred prosecution settlement terms are not a stated 60–180-day operating recovery period.
11|one_time_charge|BSBY cessation accounting charge is not a temporary operating impairment with a recovery date.
12|historical_compensation_context|Prior-year performance and previously reported FDIC/BSBY charges are directly part of the CEO compensation rationale.
13|settlement_not_operating_duration|Pilot litigation settlement does not state an ongoing temporary operating disruption.
14|planned_restructuring_or_charge|Quarterly charges and organizational simplification do not provide a dated end to an already occurring operational failure.
15|historical_compensation_context|Historical earnings decline appears as part of the CEO compensation assessment, not an unrelated new adverse disclosure.
16|no_explicit_risk_end|Regulatory penalties and remediation do not state when the operating/control risk will end.
17|transaction_not_operating_duration|Banamex sale-linked goodwill charge; second-half 2026 closing is both outside the interval and not operating-risk recovery.
18|transaction_not_operating_duration|Russian-business held-for-sale/reclassification loss is linked to a planned disposition, not a bounded temporary operating failure.
19|transaction_litigation|Merger litigation and supplemental merger disclosure do not supply an operating recovery horizon.
20|planned_restructuring_or_charge|Three-year productivity program; planned restructuring is not a temporary operating disruption with a 60–180-day recovery.
21|planned_restructuring_or_charge|Continuation of the multi-year productivity program, not a new bounded operational failure.
22|transaction_litigation|Discover accounting/restatement information appears in acquisition materials; no qualifying operating-risk resolution horizon.
23|transaction_litigation|Merger litigation supplemental disclosures, not a temporary operational impairment.
24|planned_restructuring_or_charge|Planned workforce restructuring and charge-recognition timing do not establish an ongoing disruption's end date.
25|planned_restructuring_or_charge|Planned workforce restructuring without a qualifying temporary operating failure.
26|no_explicit_risk_end|Omnicare Chapter 11 is adverse but no explicit 60–180-day operating-risk end is stated.
27|out_of_range_and_not_resolution|California production expected to continue for years; decommissioning spans a decade. Charge recognition is not recovery.
28|transaction_litigation|Merger arbitration scheduling is not the end of an ongoing operating impairment and is outside the interval.
29|transaction_not_operating_duration|FTC acquisition consent/remedies are a transaction condition, not a temporary operating-risk recovery date.
30|one_time_charge|Acquisition-related Hess severance/integration charge lacks the required ongoing operating disruption and risk-end horizon.
31|planned_restructuring_or_charge|Planned headcount reduction is not a separately evidenced temporary operating failure.
32|transaction_not_operating_duration|Star India joint-venture sale/held-for-sale impairment; transaction completion is not operating-risk resolution.
33|settlement_not_operating_duration|Fubo transaction and related litigation settlement, not a dated temporary operating disruption.
34|planned_restructuring_or_charge|European workforce restructuring and cost savings are a planned program, not operational recovery.
35|not_new_adverse_fact|Recast financial statements for the spin-off expressly do not represent a restatement.
36|settlement_not_operating_duration|Patent settlement/later generic-entry terms do not define recovery from an ongoing temporary impairment.
37|one_time_charge|China JV impairment/restructuring charge expected by December 31; 27-day accounting horizon is not operating recovery.
38|no_explicit_risk_end|EV capacity reassessment remains ongoing and further charges are possible; no recovery date is given.
39|no_explicit_risk_end|Mixed adtech antitrust decision and planned appeal have no explicit operating-risk end date.
40|settlement_not_operating_duration|Derivative settlement does not establish an ongoing operating recovery period.
41|no_explicit_risk_end|Search-distribution remedies and data-sharing obligations have no stated 60–180-day risk end.
42|one_time_charge|EC fine and cease-and-desist appeal; third-quarter accrual timing is not operating-risk resolution.
43|one_time_charge|Pension risk transfer accounting charge is not temporary operating impairment.
44|planned_restructuring_or_charge|Restructuring/impairment charges and business reorganization have no qualifying disruption recovery period.
45|planned_restructuring_or_charge|Planned workforce reduction by year-end is implementation timing, not the end of a separately evidenced operating failure.
46|planned_restructuring_or_charge|Organizational reallocation/layoffs and current-quarter charges do not establish temporary operating-risk recovery.
47|not_new_adverse_fact|FDA product clearance is positive, not an adverse operational event.
48|settlement_not_operating_duration|Proposed talc settlement and related charge are litigation-resolution mechanics, not bounded operating disruption.
49|settlement_not_operating_duration|Talc subsidiary bankruptcy supports a settlement plan; no qualifying operating-risk recovery horizon.
50|transaction_not_operating_duration|Orthopedics separation is strategic, not an adverse temporary operating disruption.
51|not_new_adverse_fact|Visa share transaction produces an accounting gain rather than an adverse event.
52|not_new_adverse_fact|Operating-segment reorganization is already completed and is not a temporary impairment.
53|one_time_charge|Pension settlement charge is accounting recognition, not a finite operating disruption.
54|settlement_not_operating_duration|Interchange litigation settlement does not specify a temporary operational recovery window.
55|settlement_not_operating_duration|Interchange litigation settlement is not an operating disruption with a dated end.
56|executive_date_not_risk_end|Ventilator wind-down directly causes the officer role elimination. April 26 is the executive departure date, not recovery.
57|not_new_adverse_fact|Diabetes spin-off is described as value-creating/accretive. Executive transition and an 18-month transaction are not bounded operating failure.
58|not_new_adverse_fact|Investor-outlook assumptions about market-rate declines do not establish an actual adverse operating event.
59|not_new_adverse_fact|Forecast assumptions do not establish an actual temporary operating impairment.
60|settlement_not_operating_duration|Derivative settlement does not state the end date of an ongoing operating disruption.
61|settlement_not_operating_duration|Earplug settlement participation and litigation obligations do not define temporary operating recovery.
62|settlement_not_operating_duration|Scheduled litigation-settlement payment is a cash obligation, not operating-risk duration.
63|already_resolved|Mine order was terminated after corrective action; no injury or continuing stated disruption.
64|settlement_not_operating_duration|PFAS settlement/charge is not a 60–180-day temporary operating recovery period.
65|planned_restructuring_or_charge|Restructuring program extends through 2031, outside the interval and not a bounded operating failure.
66|planned_restructuring_or_charge|Restructuring extends through 2027, not a 60–180-day disruption recovery.
67|already_resolved_or_unknown|Attacker access was removed; investigation continues without a stated duration and no material operational impact reported.
68|one_time_charge|Cruise investment impairment is a new financial hit but no temporary operational recovery horizon exists.
69|not_new_adverse_fact|Correction lowers reported product purchase obligations; not a new adverse operating event.
70|no_explicit_risk_end|Investigation timing cannot be predicted. Officer separation is a direct response; six-month severance is not risk duration.
71|indefinite|H20 export licensing was expressly required for the indefinite future, not 60–180 days.
72|not_new_adverse_fact|Litigation outcome favors the company; not a new adverse operating event.
73|planned_restructuring_or_charge|Multi-year manufacturing optimization is planned restructuring without a bounded current disruption.
74|planned_restructuring_or_charge|Cost program extends through 2027; no qualifying finite temporary impairment.
75|one_time_charge|Earnings-related Gillette impairment does not establish a temporary operating failure with a dated end.
76|planned_restructuring_or_charge|Two-year restructuring plan, outside the desired horizon and not an operational recovery date.
77|settlement_not_operating_duration|Patent settlement, not the dated end of an ongoing temporary operating disruption.
78|no_explicit_risk_end|ZYN.com sales suspended pending investigation; no restart or resolution date disclosed.
79|transaction_not_operating_duration|Vectura sale produces a loss; disposal timing is not recovery from temporary operating impairment.
80|not_new_adverse_fact|FDA authorization of ZYN is positive, not adverse.
81|settlement_not_operating_duration|Canadian tobacco litigation arrangement is settlement mechanics, not temporary operating-risk recovery.
82|indefinite|Huawei export license revoked immediately; no restoration date. Prior revenue expectations are not a risk-end commitment.
83|settlement_not_operating_duration|ITAR settlement/compliance obligations extend over years; payment timing is not operating recovery.
84|settlement_not_operating_duration|Deferred-prosecution settlement and near-term payment deadlines do not specify temporary operational recovery.
85|no_explicit_risk_end|MUSE ransomware disrupts airport check-in; no recovery date and RTX says no reasonably expected material company impact.
86|planned_restructuring_or_charge|Planned store closures mostly by fiscal year-end within days, not 60–180-day recovery from operational failure.
87|already_resolved|Earnings discussion describes previously completed restructuring, not a continuing bounded operational failure.
88|one_time_charge|Discontinued commercial facility impairment does not provide an operating recovery horizon.
89|one_time_charge|Earnings-period pension/restructuring charges do not provide a bounded operating disruption.
90|one_time_charge|Held-for-sale impairment in earnings is not a temporary operating impairment with a recovery date.
91|already_resolved_or_unknown|Customer-log exfiltration occurred April 14–25; investigation disclosure supplies no forward 60–180-day operating-risk end.
92|one_time_charge|Prior-quarter goodwill impairment in earnings is not a bounded future operating disruption.
93|planned_restructuring_or_charge|Workforce reduction and unplanned executive resignation supply no operational recovery date; neither is unrelated routine filler.
94|no_explicit_risk_end|Change Healthcare systems isolated; company explicitly cannot estimate incident duration or extent.
95|no_explicit_risk_end|Formal DOJ criminal/civil information requests and internal reviews supply no explicit risk-end horizon.
96|transaction_litigation|Merger supplemental litigation disclosures do not state recovery from an operating disruption.
97|not_new_adverse_fact|Consent order termination is favorable, not a new adverse operating event.
98|settlement_not_operating_duration|Interchange settlement does not state a finite temporary operational recovery window.
99|settlement_not_operating_duration|Interchange settlement does not establish a bounded operating disruption.
100|out_of_range_and_not_resolution|Wireline secular decline and five-year revised outlook cause goodwill impairment; no 60–180-day risk resolution.
101|already_resolved|BlueJeans closure was completed in 2023; subsequent earnings discussion is not a continuing temporary disruption.
102|not_new_adverse_fact|Pension remeasurement credit is favorable accounting news, not an adverse operating event.
103|already_resolved|Repeated earnings disclosure of already-closed BlueJeans business, not ongoing temporary risk.
104|planned_restructuring_or_charge|Voluntary workforce exit plan through March 2025 is planned implementation and more than 180 days away.
105|one_time_charge|Quarterly earnings charges for workforce program do not establish a disruption recovery date.
106|one_time_charge|Earnings update on existing severance and pension charges lacks finite operating recovery.
107|planned_restructuring_or_charge|Workforce exits in December 2025 are planned actions within 60 days, not operating-risk recovery.
108|settlement_not_operating_duration|Derivative settlement does not define the duration of a temporary operating impairment.
109|settlement_not_operating_duration|Derivative litigation settlement/hearing is not an operating recovery window.
'''

# Main-document review is distinguished from relevant-exhibit review below.
# Sources were opened through web; a direct SEC download returned 403 and was
# stopped. That failed direct request is recorded separately, not a successful cache.
SOURCE_PATHS = {
1: '320193/000114036124040659/ef20035718_8k.htm',
3: '1551152/000155115225000006/abbv-20250109.htm',
6: '1053507/000105350725000129/amt-20250903.htm',
12: '70858/000007085824000027/bac-20240202.htm',
15: '831001/000110465924025567/c-20240215x8k.htm',
17: '831001/000110465925092977/c-20250924x8k.htm',
27: '93410/000009341024000002/cvx-20240102.htm',
32: '1744489/000119312524049404/d800554d8k.htm',
37: '1467858/000119312524270298/d902397d8k.htm',
38: '1467858/000146785825000136/gm-20251007.htm',
41: '1652044/000165204425000067/goog-20250902.htm',
42: '1652044/000165204425000074/goog-20250905.htm',
56: '1613103/000161310324000006/mdt-20240213.htm',
57: '1613103/000161310325000078/mdt-20250521.htm',
67: '789019/000119312524011295/d708866d8k.htm',
68: '789019/000119312524275524/d865252d8k.htm',
70: '1373715/000137371524000269/now-20240724.htm',
71: '1045810/000104581025000082/nvda-20250409.htm',
82: '804328/000080432824000042/qcom-20240509.htm',
85: '101829/000010182925000036/rtx-20250919.htm',
93: '1318605/000095017024044588/tsla-20240414.htm',
94: '731766/000073176624000045/unh-20240221.htm',
95: '731766/000073176625000224/unh-20250723.htm',
100: '732712/000073271224000003/vz-20240117.htm',
}
EXHIBITS = {
56: ['1613103/000161310324000006/exhibit991-fy24q3earningsr.htm'],
57: ['1613103/000161310325000078/exhibit992-diabetesseparat.htm'],
67: ['789019/000119312524011295/d708866dex991.htm'],
}
BURIAL_NOTES = {
12: ('related_historical_context', 'Only Item 8.01 discusses CEO compensation and directly supporting past-year performance. The adverse facts are part of compensation rationale, not unrelated news.'),
15: ('related_historical_context', 'Item 8.01 CEO compensation assessment uses 2023 performance and controls initiatives as its rationale. Compensation was missed by taxonomy but recovered by manual reading.'),
56: ('related_response_actions', 'Item 2.02 introduces earnings; Item 5.02 begins with the ventilator wind-down/business combination, explicitly causing elimination of the officer role. The exit is related and follows the adverse fact.'),
57: ('not_adverse', 'Items 2.02, 5.02 and 8.01 combine earnings, an officer transition and diabetes separation. Separation is presented as growth-focused and EPS-accretive, not an adverse fact by itself.'),
68: ('qualifies', 'Item 5.07 annual-meeting results and nine vote tables precede Item 7.01. That later item announces an approximately $800m Cruise impairment, lowering quarterly EPS about $0.09 beyond prior guidance. No adverse main heading or opening summary precedes the meeting information.'),
70: ('related_response_actions', 'Item 5.02 resignation/appointment and regulatory investigation concern the same hiring-policy matter; the leadership changes are a direct response, not unrelated routine content.'),
93: ('nonroutine_adverse_combination', 'Item 5.02 unplanned executive resignation precedes Item 8.01 workforce reduction. The executive exit is itself substantive adverse news, not routine administrative filler.'),
}
# Pre-outcome comparators: dedicated goodwill/asset/investment impairment filings
# (rather than ordinary earnings releases, workforce programs, or tax charges).
# These are descriptive mechanism controls, not propensity-matched causal controls.
BURIAL_CONTROLS = [3, 17, 27, 32, 37, 38, 100]
DURATION_CONTROLS = [6, 67, 71, 78, 82, 85, 94]
CONTROL_PROMINENCE = {
3: 'Item 2.06 is the sole substantive item and leads with the clinical-program impairment.',
17: 'Combined Items 2.06 and 8.01 discuss the Banamex stake sale and the directly related impairment. The board change is part of the same transaction; exhibit 99.1 is only registered securities.',
27: 'Item 2.02 immediately announces impairment and decommissioning charges; no unrelated administrative material precedes them.',
32: 'Item 2.06 leads with Star India impairment. Subsequent Item 7.01 and the press release concern the same joint venture.',
37: 'Item 2.06 is the only substantive item and leads with China JV impairment and restructuring.',
38: 'Item 2.06 is the only substantive item; its heading and opening discussion identify the EV impairment/realignment.',
100: 'Item 8.01 immediately describes wireline deterioration and the resulting goodwill impairment.',
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (HERE/name).write_text(json.dumps(value, indent=2) + '\n')

def main():
    pool = json.loads((HERE/'duration_buried_candidates.json').read_text())
    assert pool['input_sha256'] == INPUT_SHA
    candidates = pool['candidates']
    notes = {int(i): (code, reason) for i, code, reason in
             (line.split('|', 2) for line in NOTES.strip().splitlines())}
    assert set(notes) == set(range(len(candidates)))
    annotations = []
    prefix = 'https://www.sec.gov/Archives/edgar/data/'
    for i, c in enumerate(candidates):
        assert '2024-01-01' <= c['filing_date'] <= '2025-12-31'
        sources = [c['filing_url']]
        scope = 'cached_sponsor_excerpt_screen'
        if i in SOURCE_PATHS:
            sources.append(prefix + SOURCE_PATHS[i])
            scope = 'web_primary_main_filing_review'
        if i == 78:
            sources.append('https://philipmorrisinternational.gcs-web.com/static-files/e3973bcb-22a9-4cae-b066-0cf26ae24d47')
            scope = 'issuer_primary_press_release_review'
        for path in EXHIBITS.get(i, []):
            sources.append(prefix + path)
        code, reason = notes[i]
        burial_code, burial_reason = BURIAL_NOTES.get(i, (
            'no_routine_combination_in_candidate_evidence',
            'Cached candidate evidence contains no unrelated routine administrative/compensation/meeting combination; no trigger inferred from tag counts.'))
        if i in BURIAL_CONTROLS:
            burial_code, burial_reason = 'prominent_or_related_only', CONTROL_PROMINENCE[i]
        annotations.append(dict(
            candidate_index=i, ticker=c['ticker'], filing_date=c['filing_date'],
            accession_number=c['accession_number'], sources=sources,
            review_scope=scope, full_main_filing_reviewed=i in SOURCE_PATHS,
            relevant_exhibits_reviewed=len(EXHIBITS.get(i, [])),
            duration_include=False, duration_reason_code=code,
            duration_reason=reason, risk_end_date=None,
            buried_include=i == 68, buried_reason_code=burial_code,
            buried_reason=burial_reason,
            duration_control=i in DURATION_CONTROLS,
            buried_control=i in BURIAL_CONTROLS))
    metadata = dict(
        period=['2024-01-01', '2025-12-31'],
        input_rows=pool['input_rows'], input_filings=pool['input_filings'],
        input_sha256=INPUT_SHA, candidate_filings=len(candidates),
        all_candidate_excerpts_screened=True,
        full_main_filings_reviewed=sum(a['full_main_filing_reviewed'] for a in annotations),
        issuer_release_only_reviews=1,
        relevant_exhibits_reviewed=sum(a['relevant_exhibits_reviewed'] for a in annotations),
        routine_tag_candidates=pool['with_routine_tags'],
        additional_lexical_routine_candidate='C 2024-02-20',
        audit_status='complete_for_defined_cached_candidate_pool',
        prices_or_return_outcomes_read=False,
        filings_from_2026_used=False,
        publication_rule='Use cached filing date only; execution timing is handled separately by the engine. Report/event dates in the cover are not substituted for filing dates.',
        limitations=[
            'Cached sponsor taxonomy/excerpts define the candidate screen; this is not exhaustive full-text screening of all 1,741 filings.',
            'All 110 adverse candidate excerpts were annotated; only economically plausible routine combinations, duration cases, and selected comparison filings received full-primary-source review.',
            'Direct SEC download returned 403 and was stopped; accessible web SEC/issuer sources support the recorded factual paraphrases. Raw full filings are not cached.',
            'One buried trigger cannot establish an attention effect or alpha. Controls vary by issuer and event type and are descriptive, not randomized or propensity matched.',
            'Zero duration triggers means the exact strategy is untestable in this screened sample, not disproved. No indefinite risk was relabeled as 60–180 days.',
        ])
    write('duration_buried_annotations.json', dict(metadata=metadata, annotations=annotations))
    def event(a, signal, control=False):
        result={k:a[k] for k in ('ticker','filing_date','accession_number','sources')}
        result.update(signal=signal, strategy='protective_put' if signal=='duration' else 'collar',
                      reason=a[f'{signal}_reason'], full_source_reviewed=a['full_main_filing_reviewed'] or a['review_scope']=='issuer_primary_press_release_review',
                      control=control)
        if signal == 'duration':
            result['risk_end_date'] = a['risk_end_date']
            result['control_type'] = 'operating_risk_failing_explicit_horizon'
        elif control:
            result['control_type'] = 'dedicated_impairment_without_unrelated_routine_burial'
        else:
            result.update(adverse_type='investment_impairment',routine_item='5.07',adverse_item='7.01')
        return result
    for signal in ('duration', 'buried'):
        out = dict(metadata=dict(metadata, spec_sha256=sha(HERE/f'{signal}_spec.json')),
                   events=[event(a,signal) for a in annotations if a[f'{signal}_include']],
                   controls=[event(a,signal,True) for a in annotations if a[f'{signal}_control']])
        write(f'{signal}_events.json', out)
    audit = dict(metadata=metadata,
        duration=dict(qualifying_events=0, nontrigger_controls=len(DURATION_CONTROLS),
                      exclusion_counts=dict(collections.Counter(a['duration_reason_code'] for a in annotations))),
        buried=dict(qualifying_events=1, nontrigger_controls=len(BURIAL_CONTROLS),
                    exclusion_counts=dict(collections.Counter(a['buried_reason_code'] for a in annotations if not a['buried_include'])),
                    control_selection='All source-reviewed dedicated impairment disclosures chosen before this annotator viewed any price data; exclude ordinary earnings releases, restructuring programs and tax charges.'),
        horizon_crosscheck='duration_horizon_crosscheck.json records a separate all-row date-language recall screen; none supplies a qualifying ongoing 60–180-day operating-risk recovery date.')
    write('duration_buried_audit.json', audit)
    print(json.dumps({k:v for k,v in audit.items() if k!='metadata'}, indent=2))

if __name__ == '__main__':
    main()
