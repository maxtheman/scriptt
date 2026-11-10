import { atom, read, update } from 'claude-code'
import type { EngineInterface, ProcessRunInit, Register } from 'claude-code'

import type { Mine, Reading } from '../types'

// scriptt in the app. The harness (.scriptt/harness.py in the folder of the session) does all the reading and writes the log.
// This mod runs it on each message that you type, attaches its block for Claude, and draws the reading on your own message:
// 1 line for each part. Only the items after a part's words can be pressed, never the words. The pointer on an item shows
// what a press will say. Press a function: the part does not ask for it. Press it again: it does. Pick from "?" what a part asks for.
const PYTHONS = ['python3.14', '/opt/homebrew/bin/python3.14', '/usr/local/bin/python3.14']
const HARNESS = '.scriptt/harness.py'
// Values of the "?" picker that are no function. A function name is a Python name, so neither can be one.
const UNKNOWN = '?'
const NOTHING = '-'

const readings = atom({ plugin: 'scriptt', key: 'readings' } as const, {}, { shape: 'readings-2' })
const mine = atom({ plugin: 'scriptt', key: 'mine' } as const, {})
const checks = atom({ plugin: 'scriptt', key: 'checks' } as const, {})
const open = atom({ plugin: 'scriptt', key: 'open' } as const, {})
const functions = atom({ plugin: 'scriptt', key: 'functions' } as const, [])
const world = atom({ plugin: 'scriptt', key: 'world' } as const, {})
const session = atom({ plugin: 'scriptt', key: 'session' } as const, '')
const interpreter = atom({ plugin: 'scriptt', key: 'python' } as const, '')

const reason = (error: unknown) => (error instanceof Error ? error.message : String(error))
const lastLine = (text: string) => (text.trim().split('\n').pop() ?? '').replace(/^scriptt: /, '').slice(0, 120)

// The folder that has .scriptt/harness.py: the folder of the session, or the nearest folder above it.
const UP = 'd=$PWD; while :; do [ -f "$d/.scriptt/harness.py" ] && printf %s "$d" && exit 0; [ "$d" = / ] && exit 1; d=$(dirname "$d"); done'
const home = async ($: EngineInterface) => {
  const found = await $.process.run(['sh', '-c', UP])

  if (found.exitCode !== 0 || !found.stdout) {
    throw new Error('no .scriptt/ in this folder or above it')
  }

  return found.stdout
}

// Runs the harness in that folder with the first interpreter that starts, and keeps that one for the session.
const harness = async ($: EngineInterface, args: string[], init?: ProcessRunInit) => {
  const cwd = await home($)
  let python = await read($, interpreter)

  if (!python) {
    for (const candidate of PYTHONS) {
      try {
        if ((await $.process.run([candidate, '--version'])).exitCode === 0) {
          python = candidate
          break
        }
      } catch {
        // not at this path: the next one
      }
    }

    if (!python) {
      throw new Error('python3.14 was not found')
    }

    const found = python
    await update($, interpreter, () => found)
  }

  return $.process.run([python, HARNESS, ...args], { ...init, cwd })
}

export const register: Register = on => {
  let lastText = ''

  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.isMeta || e.origin.kind !== 'composer') {
      return next(e)
    }

    let context: string | undefined
    let failed = ''

    try {
      let id = await read($, session)

      if (!id) {
        id = `app-${await $.clock.now()}`
        const made = id
        await update($, session, () => made)
      }

      if (Object.keys(await read($, world)).length === 0) {
        const described: Record<string, { asks?: string | null }> = JSON.parse((await harness($, ['world'])).stdout).functions
        const asks = Object.fromEntries(Object.entries(described).map(([name, f]) => [name, f.asks ?? '']))
        await update($, world, () => asks)
      }

      const event = { hook_event_name: 'UserPromptSubmit', session_id: id, prompt: e.text }
      const ran = await harness($, [], { stdin: JSON.stringify(event), timeoutMs: 60000 })

      if (ran.exitCode === 0 && ran.stdout.trim()) {
        context = JSON.parse(ran.stdout).hookSpecificOutput?.additionalContext
        const log = (await $.fs.read(`${await home($)}/.scriptt/events.jsonl`)).trim().split('\n')
        const record: Reading = JSON.parse(log[log.length - 1] ?? '')
        await update($, readings, all => ({ ...all, [e.text]: record }))
        lastText = e.text
        $.ui.status(undefined)
      } else {
        failed = lastLine(ran.stderr) || `the harness ended with status ${ran.exitCode} and no reading`
      }
    } catch (error) {
      failed = lastLine(reason(error))
    }

    // The row of this message stays the engine's own: it has no reading.
    if (failed) {
      $.ui.status(`${failed}: this message was not read`)
    }

    return next(context ? { ...e, context: [...(e.context ?? []), context] } : e)
  })

  // When Claude's turn ends: the harness checks the reply against each ask of the message.
  on('turn.complete', async ($, e, next) => {
    const id = await read($, session)
    const ended = await next(e)  // the reply is in the result of the turn

    if (id && lastText && ended?.text) {
      try {
        const event = { hook_event_name: 'Stop', session_id: id, last_assistant_message: ended.text }
        await harness($, [], { stdin: JSON.stringify(event), timeoutMs: 60000 })
        const log = (await $.fs.read(`${await home($)}/.scriptt/events.jsonl`)).trim().split('\n')
        const record = JSON.parse(log[log.length - 1] ?? '')

        if (record.event === 'Stop' && record.checks) {
          const of = lastText
          await update($, checks, all => ({ ...all, [of]: record.checks }))
        }
      } catch {
        // the check is extra: a turn ends the same without it
      }
    }

    return ended
  })

  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    const reading = (await read($, readings))[e.props.text]

    // The terminal has a full view of a row (ctrl+o): there the engine draws it. The other surfaces have this 1 view only.
    if (!reading || (e.props.isExpanded && e.surface === 'terminal')) {
      return next(e)
    }

    const table = $.ui.resolve(e)
    const { Box, Text, Button } = table
    const Select = 'Select' in table ? table.Select : undefined
    const text = reading.text
    const own: Mine = (await read($, mine))[text] ?? {}
    const done = (await read($, checks))[text] ?? {}
    const isOpen = (await read($, open))[text] ?? false
    const asks = await read($, world)
    const names = Object.keys(asks).length > 0 ? Object.keys(asks) : await read($, functions)

    // Your reading of a part goes to the log. Claude gets it with your next message.
    // The item changes at once. If the log does not take the reading, the item goes back and the status line says so.
    const say = async (part: number, change: (now: string[]) => string[]) => {
      const was: { before?: string[]; demands: string[] } = { demands: [] }

      await update($, mine, all => {
        was.before = all[text]?.[part]
        was.demands = change(was.before ?? reading.parts[part]?.demands ?? [])

        return { ...all, [text]: { ...(all[text] ?? {}), [part]: was.demands } }
      })

      let failed = ''

      try {
        const correction = { session: reading.session, text, part, demands: was.demands, things: {} }
        const ran = await harness($, ['reading'], { stdin: JSON.stringify(correction) })
        failed = ran.exitCode === 0 ? '' : lastLine(ran.stderr) || `the harness ended with status ${ran.exitCode}`
      } catch (error) {
        failed = lastLine(reason(error))
      }

      if (failed) {
        await update($, mine, all => {
          const rest = { ...(all[text] ?? {}) }
          delete rest[part]

          return { ...all, [text]: was.before === undefined ? rest : { ...rest, [part]: was.before } }
        })
        $.ui.status(`${failed}: your reading was not saved`)
      } else {
        $.ui.status(undefined)
      }
    }

    const call = (name: string, part: number) => {
      const demand = reading.demands.find(d => d.function === name && d.part === part)
      // The harness writes each demand as a Python expression. A type where a value belongs is an open hole.
      const python = demand?.python ?? `${name}()`

      return demand?.result ? `${python} = ${demand.result}` : python
    }

    // What a press will say, in words: drawn only while the pointer is on the item (the keyed Box around it).
    const consequence = (words: string) => (
      <Box display="none" hover={{ display: 'flex' }}>
        <Text dimColor>{words}</Text>
      </Box>
    )

    const asking = reading.parts.filter(p => p.demands.length > 0 || p.hole !== null).length
    const rows = reading.parts.map((part, n) => {
      const words = text.slice(part.start, part.end)
      const yours = own[n]
      const now = yours ?? part.demands
      const isHole = part.hole !== null && part.demands.length === 0
      // d1's items keep their order and place; a function that only you named comes after them.
      const items = isHole ? [] : [...part.demands, ...now.filter(name => !part.demands.includes(name))]

      return (
        <Box flexDirection="row" flexWrap="wrap" columnGap="sm">
          <Text>{words}</Text>
          {items.map(name => {
            const isOn = now.includes(name)
            const demand = reading.demands.find(d => d.function === name && d.part === n)
            const check = done[name]

            return (
              <Box key={`item-${n}-${name}`} flexDirection="row" columnGap="xs">
                <Button
                  key={`fn-${n}-${name}`}
                  onPress={() => say(n, cur => (cur.includes(name) ? cur.filter(other => other !== name) : [...cur, name]))}
                >
                  <Text mono weight={isOn ? 'semibold' : 'regular'} strikethrough={!isOn} dimColor={!isOn}>
                    {call(name, n)}
                  </Text>
                </Button>
                {isOpen && demand && (
                  <Text dimColor>
                    {demand.p.toFixed(2)} from {demand.by}
                  </Text>
                )}
                {isOn && check !== undefined && <Text dimColor>{check >= 0.5 ? 'done' : 'not done'}</Text>}
                {consequence(isOn ? `Press: this part does not ask for ${name}` : `Press: this part asks for ${name}`)}
              </Box>
            )
          })}
          {!isHole && yours !== undefined && now.length === 0 && <Text>nothing</Text>}
          {isHole && !Select && <Text weight="semibold">?</Text>}
          {isHole && Select && (
            <Box key={`item-${n}-hole`} flexDirection="row" columnGap="xs">
              {yours !== undefined && (
                <Text strikethrough dimColor>
                  ?
                </Text>
              )}
              <Select
                key={`hole-${n}`}
                value={yours === undefined ? UNKNOWN : (yours[0] ?? NOTHING)}
                options={[
                  ...(yours === undefined ? [{ value: UNKNOWN, label: '?' }] : []),
                  { value: NOTHING, label: 'it asks for nothing' },
                  ...names.map(name => ({ value: name, label: asks[name] ? `${name}: ${asks[name]}` : name })),
                ]}
                onSelect={value => {
                  if (value !== UNKNOWN) {
                    void say(n, () => (value === NOTHING ? [] : [value]))
                  }
                }}
              />
              {isOpen && part.hole !== null && <Text dimColor>{part.hole.toFixed(2)} asks, no function fits</Text>}
              {consequence('Pick: what this part asks for')}
            </Box>
          )}
        </Box>
      )
    })

    return (
      <Box flexDirection="column">
        {rows}
        <Box key="item-count" flexDirection="row" columnGap="xs">
          <Button
            key="count"
            label={`${asking} of ${reading.parts.length}`}
            dimColor
            onPress={() => update($, open, all => ({ ...all, [text]: !(all[text] ?? false) }))}
          />
          {consequence(isOpen ? "Press: hide d1's numbers" : "Press: show d1's numbers")}
        </Box>
        {isOpen && (
          <Box flexDirection="row" flexWrap="wrap" columnGap="sm">
            {Object.keys(reading.p)
              .filter(name => !reading.parts.some(part => part.demands.includes(name)))
              .map(name => (
                <Text dimColor>
                  <Text strikethrough>{name}</Text> {(reading.p[name] ?? 0).toFixed(2)}
                </Text>
              ))}
          </Box>
        )}
      </Box>
    )
  })
}
