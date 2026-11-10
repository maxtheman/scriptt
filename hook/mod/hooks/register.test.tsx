import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On, RenderElement } from 'claude-code'

// The kit prints what a test logs: the trees of the row in its 3 states.
declare const console: { log: (text: string) => void }

const TEXT = 'Redesign the page. Then test it. Count 3 cells.'
// 1 line of events.jsonl in form 3: part 0 asks for redesign, part 1 for test, and its "it" stands for "the page";
// part 2 is an abstention, and its "3" is a piece that no hole takes (the harness writes an int as a number).
const RECORD = {
  form: 3,
  event: 'UserPromptSubmit',
  session: 'app-0',
  text: TEXT,
  parts: [
    { start: 0, end: 18, demands: ['redesign'], hole: null, choice: 'redesign', scores: { redesign: 0.81, none: 0.1 } },
    { start: 19, end: 32, demands: ['test'], hole: null, choice: 'test', scores: { test: 0.7, none: 0.2 } },
    { start: 33, end: 47, demands: [], hole: 0.6, choice: 'none', scores: { none: 0.6, count: 0.3 } },
  ],
  pieces: [
    { id: 0, part: 0, start: 9, end: 17, words: 'the page', type: 'Surface', value: 'the page', by: 'the words', to: { demand: 0, path: 'surface' }, of: null },
    { id: 1, part: 1, start: 29, end: 31, words: 'it', type: 'Surface', value: 'the page', by: 'the piece', to: { demand: 1, path: 'surface' }, of: { piece: 0 } },
    { id: 2, part: 2, start: 39, end: 40, words: '3', type: 'int', value: 3, by: 'the words', to: null, of: null },
  ],
  demands: [
    { function: 'redesign', p: 0.81, by: 'the part', part: 0, python: "redesign(surface=Surface('the page'))",
      parameters: { surface: { type: 'Surface', value: 'the page', by: 'the words', piece: 0 } } },
    { function: 'test', p: 0.7, by: 'the part', part: 1, python: "test(surface=Surface('the page'))",
      parameters: { surface: { type: 'Surface', value: 'the page', by: 'the piece', piece: 1 } } },
  ],
  p: { redesign: 0.81, test: 0.7, count: 0.3 },
}
// The same message in form 2: no pieces, no choice, no piece in a hole.
const FORM2 = {
  ...RECORD,
  form: 2,
  pieces: undefined,
  parts: RECORD.parts.map(({ choice, ...part }) => part),
  demands: RECORD.demands.map(d => ({ ...d, parameters: { surface: { type: 'Surface', value: d.parameters.surface.value, by: d.parameters.surface.by } } })),
}
const WORLD = {
  functions: {
    redesign: { asks: 'redesign a surface', returns: 'Surface', holes: { surface: 'Surface' } },
    test: { asks: 'test a surface', returns: 'bool', holes: { surface: 'Surface' } },
    count: { asks: 'count the cells', returns: 'int', holes: { cells: 'int | None' } },
  },
  types: { Surface: { sum: ['the page', 'the mod'], doc: 'a surface that a person sees' } },
}
const ROW = { plugin: 'scriptt', component: 'UserMessage', props: { text: TEXT, origin: { kind: 'composer' }, isExpanded: true } } as const

// Stands for the machine: an interpreter, the harness and its log. `ran` gets each harness call; `status` each status line.
const machine = (on: On, { record = RECORD as object, readingExit = (): number => 0, pythons = ['python3.14'], folder = '/project' } = {}) => {
  const ran: { argv: readonly string[]; stdin?: string }[] = []
  const status: (string | undefined)[] = []
  const out = (exitCode: number, stdout = '', stderr = '') => ({
    value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false },
  })

  mock.clock(on)
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  on('fs.read', () => ({ value: `${JSON.stringify(record)}\n` }))
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

    if (args[1] === 'reading') {
      const exit = readingExit()

      return out(exit, '', exit ? 'Traceback\nStopIteration' : '')
    }

    return out(0, JSON.stringify({ hookSpecificOutput: { additionalContext: 'scriptt: 3 parts, 3 ask.' } }))
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

test('the row draws the message, its pieces and the tag of each part, and 1 button', async ($, on) => {
  machine(on)
  expect(await send($)).toMatchObject({ context: ['scriptt: 3 parts, 3 ask.'] })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...ROW, props: { ...ROW.props, isExpanded: false }, surface })
    expect((await ui.find({ type: 'Client' }))?.props).toMatchObject({ key: 'row', module: 'hooks/row.tsx' })
    await ui.resize({ columns: 160, rows: 6 })
    expect(await rows(ui)).toEqual(['Redesign the page. redesign 0.81 Then test it. test 0.70 Count 3 cells. none 0.60'])
    expect((await ui.findAll({ type: 'Button', in: 'row' })).map(b => b.key)).toEqual(['scriptt'])
    // A piece is in the colour of its type; the tag is dim.
    expect((await ui.find({ type: 'Text', text: exact('the page'), in: 'row' }))?.props).toMatchObject({ color: '#5b9cf5', underline: true })
    expect((await ui.find({ type: 'Text', text: exact('none 0.60'), in: 'row' }))?.props).toMatchObject({ dimColor: true })
    surface === 'desktop' && console.log(`default:\n${JSON.stringify(await ui.drawn({ in: 'row' }))}`)
    await ui.unmount()
  }
})

test('scriptt turns on drag mode: the calls with their holes, the mappings and the world', async ($, on) => {
  machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })

  expect(await rows(ui)).toEqual([
    'Redesign the page#1. redesign(surface=the page#1) Then test it#2=#1. test(surface=the page#2) Count 3 cells. none 0.60',
    ' ',
    'redesign test count',
    'Surface the page the mod',
    'int',
    ' ',
  ])
  // The things that can move slant on every other tick.
  const before = (await ui.find({ type: 'Text', text: exact('redesign'), in: 'row' }))?.props.italic
  await ui.advance(300)
  expect((await ui.find({ type: 'Text', text: exact('redesign'), in: 'row' }))?.props.italic).toBe(!before)
  // The pointer on "it" lights the piece that it stands for and the hole that takes it.
  const all = await rows(ui)
  await ui.pointer({ type: 'move', ...cell(all, 'Then', 'it', 'test ') })
  expect((await ui.findAll({ type: 'Text', text: exact('the page'), in: 'row' })).map(t => t.props.weight)).toEqual(['bold', undefined, 'bold', undefined])
  // The pointer on a function of the world: its docstring is the 1 line.
  await ui.pointer({ type: 'move', ...cell(all, 'redesign test count', 'count') })
  expect((await rows(ui)).at(-1)).toBe('count the cells')
  console.log(`drag mode:\n${JSON.stringify(await ui.drawn({ in: 'row' }))}`)
  await ui.unmount()
})

test('a drag of a member into a hole of its type shows what it will record, and the drop records it', async ($, on) => {
  const { ran } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  const all = await rows(ui)
  const member = cell(all, 'Surface the page', 'the mod')
  const hole = cell(all, 'test(', 'the page', 'test(surface=')
  const int = cell(all, 'Count', '3', 'Count ')

  await ui.pointer({ type: 'down', ...member, button: 'left' })
  await ui.pointer({ type: 'move', x: member.x + 1, y: member.y, button: 'left' })
  await ui.pointer({ type: 'move', ...hole, button: 'left' })
  expect((await rows(ui)).at(-1)).toBe('{"part":1,"demands":["test"],"things":{"test.surface":"the mod"}}')
  // Only the holes of its type can take it: both Surface holes are marked, the int is not.
  expect((await ui.findAll({ type: 'Text', text: exact('the page'), in: 'row' })).map(t => t.props.underline)).toEqual([undefined, true, true, undefined])
  console.log(`dragging over a hole:\n${JSON.stringify(await ui.drawn({ in: 'row' }))}`)
  // Over a thing that cannot take it, the line is empty and the dragged thing turns to the error colour.
  await ui.pointer({ type: 'move', ...int, button: 'left' })
  expect((await rows(ui)).at(-1)).toBe(' ')
  expect((await ui.find({ type: 'Text', text: exact('the mod'), in: 'row' }))?.props).toMatchObject({ dimColor: true })
  expect(JSON.stringify(await ui.drawn({ in: 'row' }))).toContain('"position":"absolute"')
  expect(JSON.stringify(await ui.drawn({ in: 'row' }))).toContain('"backgroundColor":"error"')

  await ui.pointer({ type: 'move', ...hole, button: 'left' })
  await ui.pointer({ type: 'up', ...hole, button: 'left' })
  expect(ran.at(-1)?.argv.slice(1)).toEqual(['.scriptt/harness.py', 'reading'])
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toEqual({ session: 'app-0', text: TEXT, part: 1, demands: ['test'], things: { 'test.surface': 'the mod' } })
  expect((await rows(ui))[0]).toContain('test(surface=the mod)')
  // The word "test" of the message comes first, then the function on the part.
  expect((await ui.findAll({ type: 'Text', text: exact('test'), in: 'row' }))[1]?.props).toMatchObject({ color: 'success', inverse: true })
  await ui.unmount()
})

test('a function dragged onto a part is asked for there, dragged off to the world it is not, and a pulled thing leaves an open hole', async ($, on) => {
  const { ran } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  const drag = async (from: { x: number; y: number }, to: { x: number; y: number }) => {
    await ui.pointer({ type: 'down', ...from, button: 'left' })
    await ui.pointer({ type: 'move', x: from.x + 1, y: from.y, button: 'left' })
    await ui.pointer({ type: 'move', ...to, button: 'left' })
    await ui.pointer({ type: 'up', ...to, button: 'left' })
  }

  let all = await rows(ui)
  await drag(cell(all, 'redesign test count', 'count'), cell(all, 'none 0.60', 'none'))
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toMatchObject({ part: 2, demands: ['count'], things: {} })
  // "add a hole": the type int, dropped on count, opens its hole `cells`. Then "3" fills it.
  // This one by 2 taps of the pointer: a tap picks, the next tap drops.
  all = await rows(ui)
  const tap = async (at: { x: number; y: number }) => {
    await ui.pointer({ type: 'down', ...at, button: 'left' })
    await ui.pointer({ type: 'up', ...at, button: 'left' })
  }
  await tap(cell(all, 'int', 'int'))
  await tap(cell(all, 'count(', 'count'))
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toMatchObject({ part: 2, demands: ['count'], things: { 'count.cells': null } })
  all = await rows(ui)
  expect(all.join('\n')).toContain('count(cells=int)')
  await drag(cell(all, 'Count', '3', 'Count '), cell(all, 'count(', 'int', 'cells='))
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toMatchObject({ part: 2, things: { 'count.cells': '3' } })
  // Pulled out of its hole into the world: the hole is open.
  all = await rows(ui)
  await drag(cell(all, 'redesign(', 'the page', 'surface='), cell(all, 'Surface the page', 'Surface'))
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toEqual({ session: 'app-0', text: TEXT, part: 0, demands: ['redesign'], things: { 'redesign.surface': null } })
  expect((await rows(ui))[0]).toContain('redesign(surface=Surface)')
  // A function of a part dropped on the world: the part does not ask for it.
  all = await rows(ui)
  await drag(cell(all, 'redesign(', 'redesign', 'Redesign the page#1. '), cell(all, 'redesign test count', 'test'))
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toMatchObject({ part: 0, demands: [], things: {} })
  expect((await rows(ui))[0]).toMatch(/^Redesign the page#1\. nothing Then/)
  await ui.unmount()
})

test('with no pointer event, drag mode draws buttons: press a thing, then press its hole', async ($, on) => {
  const { ran } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.press({ key: 'scriptt' })
  const buttons = await ui.findAll({ type: 'Button', in: 'row' })
  expect(buttons.map(b => b.text)).toEqual(['the page', 'redesign', 'the page', 'it', 'test', 'the page', '3', 'none 0.60', 'redesign', 'test', 'count', 'Surface', 'the page', 'the mod', 'int', 'scriptt'])
  await ui.press({ key: buttons[13]?.key ?? '' })
  await ui.press({ key: buttons[2]?.key ?? '' })
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toMatchObject({ part: 0, things: { 'redesign.surface': 'the mod' } })
  await ui.unmount()
})

test('a form 2 line: the pieces come from the hole values in the words, the choice from the demands', async ($, on) => {
  machine(on, { record: FORM2 })
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.resize({ columns: 160, rows: 12 })
  expect(await rows(ui)).toEqual(['Redesign the page. redesign 0.81 Then test it. test 0.70 Count 3 cells. none 0.60'])
  await ui.pointer({ type: 'enter', x: 0, y: 0 })
  await ui.press({ key: 'scriptt' })
  expect((await rows(ui))[0]).toBe('Redesign the page#1. redesign(surface=the page#1) Then test it. test(surface=the page) Count 3 cells. none 0.60')
  await ui.unmount()
})

test('a reading that the log does not take goes back and the status line says so', async ($, on) => {
  const { status } = machine(on, { readingExit: () => 1 })
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })
  await ui.press({ key: 'scriptt' })
  const buttons = await ui.findAll({ type: 'Button', in: 'row' })
  await ui.press({ key: buttons[13]?.key ?? '' })
  await ui.press({ key: buttons[2]?.key ?? '' })
  expect(status.at(-1)).toBe('StopIteration: your reading was not saved')
  expect((await ui.findAll({ type: 'Button', in: 'row' }))[2]?.text).toBe('the page')
  expect((await ui.find({ type: 'Text', text: exact('redesign'), in: 'row' }))?.props).toMatchObject({ color: 'error' })
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
