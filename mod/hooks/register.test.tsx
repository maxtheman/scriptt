import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On, RenderElement } from 'claude-code'

// The kit prints what a test logs: the trees of the row in its 3 states.
declare const console: { log: (text: string) => void }

const TEXT = 'Redesign the page. Then show it. Count 3 cells.'
// 1 snapshot of a reading in .scriptt/events.jsonl (form 5), as scriptt16.record wrote it for this message with the stand-in d1
// (its decisions left out): phrase 0 asks for redesign of the page, phrase 1 to show its result (#0), and phrase 2 is unresolved.
const RECORD = {
  form: 5, id: 'r1', text: TEXT, source: '2f36b9550c7773a2', world: 'b193ec94c1e33177', base: null, snapshot: 's1',
  phrases: [
    { start: 0, end: 19, brand: 'Asked', starts_by: 'the first word', quotes: null, unresolved: [],
      terms: [{ id: '0', function: 'redesign', type: 'Later[Surface]', parameters: { surface: 'Surface' }, arguments: { surface: { constant: 'the page', type: 'Surface', at: [9, 17] } } }] },
    { start: 19, end: 33, brand: 'Asked', starts_by: 'after .', quotes: null, unresolved: [],
      terms: [{ id: '1', function: 'show', type: 'Subject', parameters: { subject: 'Subject' }, arguments: { subject: { ref: '0' } } }] },
    { start: 33, end: 47, brand: 'Asked', starts_by: 'after .', quotes: null, terms: [], unresolved: [{ id: '2', reason: 'rejected', place: 0 }] },
  ],
  constants: [{ constant: 'the page', type: 'Surface', at: [9, 17] }],
  decisions: [],
  corrections: [],
}
// The session that sent it, as .scriptt/hooks.jsonl names it.
const SENT = { event: 'UserPromptSubmit', session: 'app-0', reading: 'r1', snapshot: 's1' }
const asked = { brand: 'Asked', of: { brand: 'Words', of: { base: 'str' } } }
const SURFACE = { sum: 'Surface', alternatives: [{ member: 'PAGE', words: 'the page', type: asked }, { member: 'MOD', words: 'the mod', type: asked }] }
const CODE = { sum: 'Code', alternatives: [{ member: 'SEARCH', words: 'the search', type: asked }] }
const SUBJECT = { sum: 'Subject', alternatives: [SURFACE, CODE, { base: 'Path' }] }
// `harness.py world`: agree.world_record of a world with these 3 functions.
const WORLD = {
  identity: 'b193ec94c1e33177',
  types: { Surface: { ...SURFACE, kind: '*' }, Code: { ...CODE, kind: '*' }, Path: { base: 'Path', kind: '*' }, Subject: { ...SUBJECT, kind: '*' } },
  functions: {
    redesign: { asks: 'change how the page looks', parameters: [['surface', SURFACE]], result: { constructor: 'Later', of: SURFACE } },
    show: { asks: 'show something so that the user can see it', parameters: [['subject', SUBJECT]], result: SUBJECT },
    explain: { asks: 'explain something', parameters: [['subject', { constructor: 'Maybe', of: { brand: 'Words', of: { base: 'str' } } }]], result: { brand: 'Written', of: { brand: 'Words', of: { base: 'str' } } } },
  },
}
// The reading with a correction at #1 subject: what `harness.py post /accept` saves for a value.
const corrected = (subject: object) => ({
  ...RECORD,
  snapshot: 's2',
  phrases: RECORD.phrases.map((p, n) => (n === 1 ? { ...p, terms: [{ ...p.terms[0], arguments: { subject } }] } : p)),
  corrections: [{ operation: 1, path: 'subject', status: 'retained' }],
})
const ROW = { plugin: 'scriptt', component: 'UserMessage', props: { text: TEXT, origin: { kind: 'composer' }, isExpanded: true } } as const

// Stands for the machine: an interpreter, the harness and its 2 files. `ran` gets each harness call; `status` each status line.
// accept: what `harness.py post /accept` answers for a body.
const machine = (on: On, { record = RECORD as object, accept = (body: { value: object }): object => ({ saved: corrected(body.value), diagnostics: [] }), pythons = ['python3.14'], folder = '/project' } = {}) => {
  const ran: { argv: readonly string[]; stdin?: string }[] = []
  const status: (string | undefined)[] = []
  const out = (exitCode: number, stdout = '', stderr = '') => ({
    value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false },
  })

  mock.clock(on)
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  on('fs.read', (_, e) => ({ value: `${JSON.stringify(e.path.endsWith('hooks.jsonl') ? SENT : record)}\n` }))
  on('ui.status', (_, e) => {
    status.push(e.text)

    return { value: undefined }
  })
  on('process.run', (_, e) => {
    const [python = '', ...args] = e.argv

    if (python === 'sh') {
      return folder ? out(0, folder) : out(1)
    }

    if (!pythons.includes(python)) {
      return out(127, '', 'not found')
    }

    if (args[0] === '--version') {
      return out(0, 'Python 3.14.0')
    }

    ran.push({ argv: e.argv, stdin: e.init?.stdin })

    if (args[1] === 'world') {
      return out(0, JSON.stringify(WORLD))
    }

    if (args[1] === 'post') {
      return out(0, JSON.stringify(accept(JSON.parse(e.init?.stdin ?? '{}'))))
    }

    return out(0, JSON.stringify({ hookSpecificOutput: { additionalContext: 'scriptt: 3 obligations.' } }))
  })

  return { ran, status }
}

const send = ($: Engine) => $.prompt.submit({ text: TEXT, wait: false, origin: { kind: 'composer' } })
const exact = (text: string) => new RegExp(`^${text.replace(/[.()]/g, c => `\\${c}`)}$`)
const words = (node: unknown): string =>
  typeof node === 'string' ? node : ((node as { children?: unknown[] }).children ?? []).map(words).join('')
// The rows that the row module draws, as text: 1 string for each row of cells, the 1 line last in drag mode.
const rows = async (ui: { drawn: (scope?: { in?: string }) => Promise<RenderElement> }) =>
  (((await ui.drawn({ in: 'row' })) as { children?: { type?: string }[] }).children ?? []).filter(c => c.type === 'Text').map(words)
// The cell of the first place of `what` on the row that holds `on`, after `after` on that row.
const cell = (all: string[], on: string, what: string, after = '') => {
  const y = all.findIndex(row => row.includes(on))
  const row = all[y] ?? ''

  return { x: row.indexOf(what, row.indexOf(after) + after.length), y }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- the mounted surface's pointer event type
const drag = async (ui: { pointer: (p: any) => Promise<unknown> }, from: { x: number; y: number }, to: { x: number; y: number }) => {
  await ui.pointer({ type: 'down', ...from, button: 'left' })
  await ui.pointer({ type: 'move', x: from.x + 1, y: from.y, button: 'left' })
  await ui.pointer({ type: 'move', ...to, button: 'left' })
  await ui.pointer({ type: 'up', ...to, button: 'left' })
}
const DEFAULT = 'Redesign the page. #0 redesign Then show it. #1 show Count 3 cells. #2 ?'

test('the row draws the message, its values and the obligations of each phrase, a link to the board, and 1 button', async ($, on) => {
  machine(on)
  expect(await send($)).toMatchObject({ context: ['scriptt: 3 obligations.'] })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...ROW, props: { ...ROW.props, isExpanded: false }, surface })
    expect((await ui.find({ type: 'Client' }))?.props).toMatchObject({ key: 'row', module: 'hooks/row.tsx' })
    expect((await ui.find({ type: 'Link' }))?.props).toMatchObject({ href: 'http://localhost:8787/?reading=r1' })
    await ui.resize({ columns: 160, rows: 6 })
    expect((await rows(ui)).map(r => r.replace(/ +/g, ' '))).toEqual([DEFAULT])
    expect((await ui.findAll({ type: 'Button', in: 'row' })).map(b => b.key)).toEqual(['scriptt'])
    // A value of the message is in the colour of its type; the tag is dim.
    expect((await ui.find({ type: 'Text', text: exact('the page'), in: 'row' }))?.props).toMatchObject({ color: '#5b9cf5', underline: true })
    expect((await ui.find({ type: 'Text', text: exact('#1 show'), in: 'row' }))?.props).toMatchObject({ dimColor: true })
    surface === 'desktop' && console.log(`default:\n${JSON.stringify(await ui.drawn({ in: 'row' }))}`)
    await ui.unmount()
  }
})

test('scriptt turns on drag mode: the calls with their holes, the result of #0 in #1, and the world', async ($, on) => {
  machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  const all = (await rows(ui)).map(r => r.replace(/ +/g, ' '))
  console.log(`drag mode:\n${all.join('\n')}`)
  expect(all[0]).toBe('Redesign the page#1. redesign(surface=the page#1) Then show it. show(subject=#0) Count 3 cells. #2 ?')
  expect(all.slice(2, 5)).toEqual(['redesign show explain', 'Surface the page the mod', 'Code the search'])
  await ui.unmount()
})

test('a member dragged into a hole of a union that takes its type is a correction that the engine saves', async ($, on) => {
  const { ran } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  const all = await rows(ui)
  const member = cell(all, 'Surface the page', 'the mod')
  const hole = cell(all, 'show(', '#0', 'show(subject=')
  await ui.pointer({ type: 'down', ...member, button: 'left' })
  await ui.pointer({ type: 'move', x: member.x + 1, y: member.y, button: 'left' })
  await ui.pointer({ type: 'move', ...hole, button: 'left' })
  expect((await rows(ui)).at(-1)).toBe('{"part":1,"demands":["show"],"things":{"show.subject":"the mod"}}')
  await ui.pointer({ type: 'up', ...hole, button: 'left' })
  expect(ran.at(-1)?.argv.slice(1)).toEqual(['.scriptt/harness.py', 'post', '/accept'])
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toEqual({ reading: 'r1', number: 1, path: 'subject', value: { constant: 'the mod', type: 'Surface', at: [-1, -1] } })
  expect((await rows(ui))[0]).toContain('show(subject=the mod)')
  expect((await ui.findAll({ type: 'Text', text: exact('show'), in: 'row' }))[1]?.props).toMatchObject({ color: 'success' })  // the message's word, then the call
  await ui.unmount()
})

test('a value pulled out of its hole onto the world clears it; a function moved is no correction yet and goes back', async ($, on) => {
  const { ran, status } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  let all = await rows(ui)
  await drag(ui, cell(all, 'redesign(', 'the page', 'surface='), cell(all, 'Surface the page', 'Surface'))
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toEqual({ reading: 'r1', number: 0, path: 'surface', value: { hole: 'Surface', reason: 'cleared' } })
  all = await rows(ui)
  const calls = ran.length
  await drag(ui, cell(all, 'redesign show explain', 'explain'), cell(all, '#2 ?', '#2'))
  expect(ran.length).toBe(calls)
  expect(status.at(-1)).toBe('adding or removing a function is not a correction the engine takes yet: your change was not saved')
  expect((await rows(ui))[0]).toContain('#2 ?')
  await ui.unmount()
})

test('a correction that the engine refuses goes back and the status line names its diagnostics', async ($, on) => {
  const { status } = machine(on, { accept: () => ({ saved: null, diagnostics: [[1, 'subject', 'type']] }) })
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.press({ key: 'scriptt' })
  const buttons = await ui.findAll({ type: 'Button', in: 'row' })
  await ui.press({ key: buttons.find(b => b.text === 'the mod')?.key ?? '' })
  await ui.press({ key: buttons.find(b => b.text === '#0')?.key ?? '' })
  expect(status.at(-1)).toBe('the engine refused it: 1 subject type: your change was not saved')
  expect((await ui.findAll({ type: 'Button', in: 'row' })).map(b => b.text)).toContain('#0')
  await ui.unmount()
})

test('the outcomes of the check at the end of the turn are in the tags, and a FAIL is struck through', async ($, on) => {
  machine(on, { record: { ...RECORD, fulfillment: [
    { obligation: 0, criterion: 'evidence', outcome: 'FAIL', evidence: 0, claim: 0.9 },
    { obligation: 1, criterion: 'evidence', outcome: 'UNVERIFIED', evidence: null, claim: 0.1 },
    { obligation: 2, criterion: 'evidence', outcome: 'UNVERIFIED', evidence: null, claim: null },
  ] } })
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  expect((await rows(ui))[0]?.replace(/ +/g, ' ')).toBe('Redesign the page. #0 redesign FAIL Then show it. #1 show UNVERIFIED Count 3 cells. #2 ?')
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  expect((await ui.find({ type: 'Text', text: exact('redesign'), in: 'row' }))?.props).toMatchObject({ strikethrough: true })
  expect((await ui.find({ type: 'Text', text: exact('show'), in: 'row' }))?.props.strikethrough).toBeUndefined()
  await ui.unmount()
})

test('the second interpreter is used when the first is not found', async ($, on) => {
  const { ran, status } = machine(on, { pythons: ['/opt/homebrew/bin/python3.14'] })
  await send($)
  expect(ran.every(call => call.argv[0] === '/opt/homebrew/bin/python3.14')).toBe(true)
  expect(status.at(-1)).toBeUndefined()
})

test("with no interpreter the row stays the engine's own and the status line says why", async ($, on) => {
  const { status } = machine(on, { pythons: [] })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text>engine</Text>
  })
  expect(await send($)).toMatchObject({ text: TEXT })
  expect(status).toEqual(['python3.14 was not found: this message was not read'])
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
  await ui.unmount()
})

test('with no .scriptt/ in the folder or above it the status line says so first', async ($, on) => {
  const { status } = machine(on, { folder: '' })
  expect(await send($)).toMatchObject({ text: TEXT })
  expect(status).toEqual(['no .scriptt/ in this folder or above it: this message was not read'])
})

test('a row in full view is drawn on the desktop, and left to the engine on the terminal and on a surface with no Client', async ($, on) => {
  machine(on)
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text>engine</Text>
  })
  await send($)
  const desktop = await $.ui.mount({ ...ROW, surface: 'desktop' })
  expect((await desktop.find({ type: 'Client' }))?.key).toBe('row')
  await desktop.unmount()

  for (const surface of ['terminal', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...ROW, surface })
    expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
    await ui.unmount()
  }
})
