export const meta = {
  name: 'pokerface-utterance-labels',
  description: 'Label masked CEO utterances (claim / denial / forward-looking / hedge) per video; agents see only masked text, never names, dates or prices',
  phases: [{ title: 'Label', detail: 'one agent per batch of ~15 videos' }],
}

// Run from the main session with: Workflow({scriptPath: 'agentic/label_workflow.js', args: {n: <num batches>}})
// Batches come from agentic/prepare_label_batches.py (.scratch/labels/batch_NNN.json).
const ROOT = '/Users/ojasvamishra32/pokerface'
const N = args && args.n ? args.n : 0
const SCHEMA = {
  type: 'object',
  properties: {
    videos: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          video_id: { type: 'string' },
          n_utterances: { type: 'integer' },
          factual_claims: { type: 'integer', description: 'utterances asserting a checkable fact about the company/results/products' },
          numeric_claims: { type: 'integer', description: 'factual claims that include a number or magnitude' },
          denials: { type: 'integer', description: 'utterances rejecting a premise, rumor, report or accusation (e.g. "that is not true", "we are not doing X", "no plans to")' },
          forward_promises: { type: 'integer', description: 'commitments or predictions about future company outcomes, timelines or products' },
          hedges: { type: 'integer', description: 'utterances dominated by qualification or uncertainty' },
          deflections: { type: 'integer', description: 'answers that avoid the question or redirect' },
          mean_certainty: { type: 'number', description: '0-3 average expressed certainty over substantive utterances' },
          mean_specificity: { type: 'number', description: '0-3 average concreteness (names of things, numbers, dates) over substantive utterances' },
          strongest_denial: { type: 'string', description: 'the clearest denial, verbatim from the masked text, <= 25 words, or empty' },
          speaker_identifiable: { type: 'boolean', description: 'true if despite masking you can tell who the speaker or company is (leak test)' },
        },
        required: ['video_id', 'n_utterances', 'factual_claims', 'numeric_claims', 'denials', 'forward_promises', 'hedges',
                   'deflections', 'mean_certainty', 'mean_specificity', 'strongest_denial', 'speaker_identifiable'],
      },
    },
  },
  required: ['videos'],
}

const prompt = (i) => `You are labeling what a corporate executive SAYS in interview answers, for a finance research project.
Read ${ROOT}/.scratch/labels/batch_${String(i).padStart(3, '0')}.json: a list of {video_id, utterances[]}. Names, companies,
products, tickers, years, dates and exact numbers are masked ([CEO], [COMPANY], [PRODUCT], [YEAR], [NUM], ...).
For EACH video, count utterances by type (an utterance can count in more than one type): factual claims, numeric claims,
denials, forward-looking promises, hedges, deflections; rate average certainty and specificity 0-3. Quote the single
clearest denial verbatim (<= 25 words) or leave empty.
Rules: judge only the text you are given. Do NOT try to identify the speaker or company, and do NOT use any outside
knowledge of what later happened; set speaker_identifiable=true if the text still reveals who it is despite masking.
Return one entry per video_id in the file.`

phase('Label')
const out = []
for (let s = 0; s < N; s += 5) {
  const idx = []
  for (let i = s; i < Math.min(s + 5, N); i++) idx.push(i)
  const r = await parallel(idx.map(i => () => agent(prompt(i), { label: `label:${i}`, phase: 'Label', schema: SCHEMA, model: 'sonnet', effort: 'low' })))
  r.forEach((x, k) => out.push({ batch: idx[k], videos: x ? x.videos : null }))
  log(`batches ${s}-${s + idx.length - 1} done`)
}
return { out }
