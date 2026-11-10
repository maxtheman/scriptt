import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const TEXT = 'Get rid of the old cells. Go look at the research.'
// 1 line of events.jsonl as harness.py writes it: part 0 asks for delete, part 1 is an abstention.
const RECORD = {
  event: 'UserPromptSubmit',
  session: 'app-0',
  text: TEXT,
  parts: [
    { start: 0, end: 25, demands: ['delete'], hole: null },
    { start: 26, end: 50, demands: [], hole: 0.84 },
  ],
  demands: [
    {
      function: 'delete',
      p: 0.98,
      by: 'the message',
      part: 0,
      parameters: { notebook: { type: 'Notebook', value: 'the old cells', by: 'the words' } },
      python: "delete(notebook=Notebook('the old cells'))",
    },
  ],
  p: { delete: 0.98, explain: 0.12 },
}
const WORLD = { functions: { delete: { asks: 'remove cells from a notebook' }, explain: { asks: 'say how a thing works' } } }
const ROW = { plugin: 'scriptt', component: 'UserMessage', props: { text: TEXT, origin: { kind: 'composer' }, isExpanded: false } } as const

// Stands for the machine: an interpreter, the harness and its log. `ran` gets each harness call; `status` each status line.
const machine = (on: On, readingExit = () => 0, pythons = ['python3.14'], folder = '/project') => {
  const ran: { argv: readonly string[]; stdin?: string }[] = []
  const status: (string | undefined)[] = []
  const out = (exitCode: number, stdout = '', stderr = '') => ({
    value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false },
  })

  mock.clock(on)
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  on('fs.read', () => ({ value: `${JSON.stringify(RECORD)}\n` }))
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

    return out(0, JSON.stringify({ hookSpecificOutput: { additionalContext: 'scriptt: 2 parts, 2 ask.' } }))
  })

  return { ran, status }
}

const send = ($: Engine) => $.prompt.submit({ text: TEXT, wait: false, origin: { kind: 'composer' } })

test('a part that asks for a function draws the function item, and only items are pressable', async ($, on) => {
  machine(on)
  expect(await send($)).toMatchObject({ context: ['scriptt: 2 parts, 2 ask.'] })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...ROW, surface })
    const item = await ui.find({ key: 'fn-0-delete' })

    expect(item?.type).toBe('Button')
    expect(item?.text).toBe("delete(notebook=Notebook('the old cells'))")
    expect((await ui.find({ type: 'Text', text: /^delete\(/ }))?.props).toMatchObject({ strikethrough: false, weight: 'semibold' })
    // What the press will say is in the tree, hidden until the pointer is on the item.
    expect(JSON.stringify(await ui.drawn())).toContain(
      '"props":{"display":"none"},"hover":{"display":"flex"},"children":[{"type":"Text","props":{"dimColor":true},"children":["Press: this part does not ask for delete"]}]',
    )
    // The buttons are the function item and the count: the part's words are a Text.
    expect((await ui.findAll({ type: 'Button' })).map(b => b.key)).toEqual(['fn-0-delete', 'count'])
    // The "?" picker: each option is an answer.
    const picker = await ui.find({ key: 'hole-1' })
    expect(picker?.props.options).toEqual([
      { value: '?', label: '?' },
      { value: '-', label: 'it asks for nothing' },
      { value: 'delete', label: 'delete: remove cells from a notebook' },
      { value: 'explain', label: 'explain: say how a thing works' },
    ])
    await ui.unmount()
  }
})

test('a press records your reading and strikes the item of d1; a second press restores it', async ($, on) => {
  const { ran } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })

  await ui.press({ key: 'fn-0-delete' })
  expect(ran.at(-1)?.argv.slice(1)).toEqual(['.scriptt/harness.py', 'reading'])
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toEqual({ session: 'app-0', text: TEXT, part: 0, demands: [], things: {} })
  expect((await ui.find({ type: 'Text', text: /^delete\(/ }))?.props).toMatchObject({ strikethrough: true, dimColor: true, weight: 'regular' })
  expect(await ui.find({ type: 'Text', text: /^nothing$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Press: this part asks for delete$/ })).toBeDefined()

  await ui.press({ key: 'fn-0-delete' })
  expect(JSON.parse(ran.at(-1)?.stdin ?? '').demands).toEqual(['delete'])
  expect((await ui.find({ type: 'Text', text: /^delete\(/ }))?.props).toMatchObject({ strikethrough: false, weight: 'semibold' })
  expect(await ui.find({ type: 'Text', text: /^nothing$/ })).toBeUndefined()
  await ui.unmount()
})

test('a reading that the log does not take puts the item back and the status line says so', async ($, on) => {
  const { status } = machine(on, () => 1)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })

  await ui.press({ key: 'fn-0-delete' })
  expect((await ui.find({ type: 'Text', text: /^delete\(/ }))?.props).toMatchObject({ strikethrough: false })
  expect(status.at(-1)).toBe('StopIteration: your reading was not saved')
  await ui.unmount()
})

test('a pick from "?" is your reading, and the count opens the numbers of d1', async ($, on) => {
  const { ran } = machine(on)
  await send($)
  const ui = await $.ui.mount({ ...ROW, surface: 'desktop' })

  await ui.select({ key: 'hole-1', value: 'explain' })
  expect(JSON.parse(ran.at(-1)?.stdin ?? '')).toMatchObject({ part: 1, demands: ['explain'] })
  expect((await ui.find({ key: 'hole-1' }))?.props.value).toBe('explain')
  expect((await ui.find({ type: 'Text', text: /^\?$/ }))?.props).toMatchObject({ strikethrough: true })

  expect((await ui.find({ key: 'count' }))?.text).toBe('2 of 2')
  await ui.press({ key: 'count' })
  expect(await ui.find({ type: 'Text', text: '0.98 from the message' })).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /^explain 0\.12$/ }))?.props).toMatchObject({ dimColor: true })
  expect(await ui.find({ type: 'Text', text: "Press: hide d1's numbers" })).toBeDefined()
  await ui.unmount()
})

test('the second interpreter is used when the first is not found', async ($, on) => {
  const { ran, status } = machine(on, () => 0, ['/opt/homebrew/bin/python3.14'])
  await send($)
  expect(ran.every(call => call.argv[0] === '/opt/homebrew/bin/python3.14')).toBe(true)
  expect(status.at(-1)).toBeUndefined()
})

test('with no interpreter the row stays the engine\'s own and the status line says why', async ($, on) => {
  const { status } = machine(on, () => 0, [])
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
  const { status } = machine(on, () => 0, ['python3.14'], '')
  expect(await send($)).toMatchObject({ text: TEXT })
  expect(status).toEqual(['no .scriptt/ in this folder or above it: this message was not read'])
})

test('a row in full view is drawn with the reading on the desktop, and left to the engine on the terminal', async ($, on) => {
  machine(on)
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text>engine</Text>
  })
  await send($)
  const full = { ...ROW, props: { ...ROW.props, isExpanded: true } }
  const desktop = await $.ui.mount({ ...full, surface: 'desktop' })
  expect((await desktop.find({ key: 'fn-0-delete' }))?.type).toBe('Button')
  await desktop.unmount()
  const terminal = await $.ui.mount({ ...full, surface: 'terminal' })
  expect((await terminal.find({ type: 'Text' }))?.text).toBe('engine')
  await terminal.unmount()
})
