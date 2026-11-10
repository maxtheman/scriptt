import { atom, read, update } from 'claude-code'
import type { EngineInterface, ProcessRunInit, Register } from 'claude-code'

import type { Change, Mine, Piece, Reading, View, ViewPiece, World } from '../types'

// scriptt in the app. The harness (.scriptt/harness.py in the folder of the session) does all the reading and writes the log.
// This mod runs it on each message that you type, attaches its block for Claude, and hands the reading of your own message
// to hooks/row.tsx, which draws it on the message and lets you move its pieces. A drop there comes back here as a ui.message
// and goes to the log through `harness.py reading`.
const PYTHONS = ['python3.14', '/opt/homebrew/bin/python3.14', '/usr/local/bin/python3.14']
const HARNESS = '.scriptt/harness.py'
// 1 colour for each type, in the order that the world and the message name the types. The status colours stay out of it.
const COLOURS = ['#5b9cf5', '#e5a33a', '#b07ee8', '#3fb8c4', '#ee78b0', '#8f9df7', '#c9b037', '#f08a4b', '#6cc4f0', '#c58fd8']

const readings = atom({ plugin: 'scriptt', key: 'readings' } as const, {}, { shape: 'readings-2' })
const mine = atom({ plugin: 'scriptt', key: 'mine' } as const, {}, { shape: 'mine-3' })
const said = atom({ plugin: 'scriptt', key: 'said' } as const, {})
const checks = atom({ plugin: 'scriptt', key: 'checks' } as const, {})
const world = atom({ plugin: 'scriptt', key: 'world' } as const, { functions: {}, types: {} }, { shape: 'world-3' })
const session = atom({ plugin: 'scriptt', key: 'session' } as const, '')
const interpreter = atom({ plugin: 'scriptt', key: 'python' } as const, '')

const reason = (error: unknown) => (error instanceof Error ? error.message : String(error))
const lastLine = (text: string) => (text.trim().split('\n').pop() ?? '').replace(/^scriptt: /, '').slice(0, 120)
const one = (type: string) => type.split('|').map(t => t.trim()).find(t => t !== 'None') ?? type

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

// Form 2 has no pieces: each hole value that the part's own words hold is one, at its first place in the part.
const piecesOf = (r: Reading): Piece[] => {
  if (r.pieces) {
    return r.pieces
  }

  const out: Piece[] = []

  r.demands.forEach((d, demand) => {
    const part = d.part === null ? undefined : r.parts[d.part]

    for (const [path, hole] of Object.entries(d.parameters)) {
      const value = hole.value == null ? '' : String(hole.value)
      const at = part && value ? r.text.slice(part.start, part.end).toLowerCase().indexOf(value.toLowerCase()) : -1

      if (part && value && at >= 0) {
        const start = part.start + at
        const end = start + value.length

        if (!out.some(p => p.start < end && start < p.end)) {
          const words = r.text.slice(start, end)
          out.push({ id: out.length, part: d.part ?? 0, start, end, words, type: one(hole.type), value, by: hole.by ?? '', to: { demand, path }, of: null })
        }
      }
    }
  })

  return out.sort((a, b) => a.start - b.start)
}

// The reading of 1 message as the row draws it: d1's reading with the user's own over it.
const viewOf = (r: Reading, own: Mine, saved: Record<string, boolean>, done: Record<string, number>, w: World): View => {
  const pieces = piecesOf(r)
  const types = [...Object.keys(w.types), ...Object.values(w.functions).flatMap(f => Object.values(f.holes).map(one)), ...pieces.map(p => p.type)]
  const named = [...new Set(types)].filter(t => !w.types[t]?.fields)
  const colours = Object.fromEntries(named.map((t, n) => [t, COLOURS[n % COLOURS.length] ?? 'text']))

  const parts = r.parts.map((part, n) => {
    const yours = own[n]
    const demands = yours?.demands ?? part.demands
    const things = yours?.things ?? {}
    const choice = part.choice ?? part.demands[0] ?? (part.hole !== null ? 'none' : 'nothing')
    const score = part.scores?.[choice] ?? r.demands.find(d => d.part === n && d.function === choice)?.p ?? part.hole
    const tag = yours ? demands.join(' ') || 'nothing' : `${part.demands.join(' ') || choice}${score == null ? '' : ` ${score.toFixed(2)}`}`

    const calls = demands.map(fn => {
      const index = r.demands.findIndex(d => d.part === n && d.function === fn)
      const d1 = r.demands[index]?.parameters ?? {}
      const all = w.functions[fn]?.holes ?? {}
      const paths = [...Object.keys(d1), ...Object.keys(things).filter(k => k.startsWith(`${fn}.`)).map(k => k.slice(fn.length + 1))]
      const shown = [...new Set(paths)]
      const holes = shown.map(path => {
        const key = `${fn}.${path}`
        // The harness may write a number (an int); the row and the reading take text.
        const value = key in things ? (things[key] ?? null) : d1[path]?.value == null ? null : String(d1[path]?.value)
        const by = key in things
          ? pieces.find(p => String(p.value) === value)
          : pieces.find(p => p.id === d1[path]?.piece) ?? pieces.find(p => p.to?.demand === index && p.to.path === path)

        return { path, type: one(d1[path]?.type ?? all[path] ?? 'str'), value, piece: value === null ? null : (by?.id ?? null) }
      })
      const hidden = Object.entries(all).filter(([path]) => !shown.includes(path)).map(([path, type]) => ({ path, type: one(type) }))

      return { fn, holes, hidden, check: done[fn] ?? null }
    })

    return { start: part.start, end: part.end, tag, demands, things, calls, said: saved[n] ?? null }
  })

  return {
    text: r.text,
    colours,
    parts,
    pieces: pieces.map((p): ViewPiece => ({ id: p.id, start: p.start, end: p.end, type: p.type, value: String(p.value), of: p.of && !p.of.at ? p.of.piece : null })),
    functions: Object.entries(w.functions).map(([name, f]) => ({ name, asks: f.asks ?? '' })),
    types: named.map(name => ({ name, doc: w.types[name]?.doc ?? '', members: w.types[name]?.sum ?? [] })),
  }
}

export const register: Register = on => {
  let lastText = ''
  // A row module that failed on a surface: the rows go back to the app's own drawing until the mod loads again.
  let fault = ''

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

      const described: World = JSON.parse((await harness($, ['world'])).stdout)
      await update($, world, () => described)

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

    // The terminal has a full view of a row (ctrl+o): there the engine draws it. A surface with no Client draws its own row.
    if (!reading || fault || (e.surface !== 'desktop' && e.surface !== 'terminal') || (e.props.isExpanded && e.surface === 'terminal')) {
      return next(e)
    }

    const { Box, Client } = $.ui.resolve(e)
    const text = reading.text
    const props = viewOf(reading, (await read($, mine))[text] ?? {}, (await read($, said))[text] ?? {}, (await read($, checks))[text] ?? {}, await read($, world))

    return (
      <Box width="100%">
        <Client key="row" module="./row.tsx" width="100%" props={props} />
      </Box>
    )
  })

  // A press or a drop in the row: the user's reading of 1 or 2 parts. Each goes to the log; the row shows it at once.
  // If the log does not take one, that part goes back and the status line says why.
  on('ui.message', async ($, e, next) => {
    const data = (e.data ?? {}) as { text?: unknown; changes?: unknown }
    const reading = typeof data.text === 'string' ? (await read($, readings))[data.text] : undefined

    for (const raw of reading && Array.isArray(data.changes) ? (data.changes as Partial<Change>[]) : []) {
      if (!reading || typeof raw.part !== 'number' || !reading.parts[raw.part] || !Array.isArray(raw.demands) || typeof raw.things !== 'object') {
        continue
      }

      const { text, session: id } = reading
      const part = raw.part
      const demands = raw.demands.filter(name => typeof name === 'string')
      const things = Object.fromEntries(Object.entries(raw.things ?? {}).filter(([, v]) => v === null || typeof v === 'string'))
      const was: { before?: Omit<Change, 'part'> } = {}

      await update($, mine, all => {
        was.before = all[text]?.[part]

        return { ...all, [text]: { ...(all[text] ?? {}), [part]: { demands, things } } }
      })

      let failed = ''

      try {
        const ran = await harness($, ['reading'], { stdin: JSON.stringify({ session: id, text, part, demands, things }) })
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
      }

      await update($, said, all => ({ ...all, [text]: { ...(all[text] ?? {}), [part]: !failed } }))
      $.ui.status(failed ? `${failed}: your reading was not saved` : undefined)
    }

    return next(e)
  })

  on('ui.fault', async ($, e, next) => {
    fault = e.reason
    $.ui.status(`${e.reason}: the app draws the rows`)

    return next(e)
  })
}
