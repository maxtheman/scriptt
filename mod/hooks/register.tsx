import { atom, read, update } from 'claude-code'
import type { EngineInterface, ProcessRunInit, Register } from 'claude-code'

import type { Accepted, Change, Mine, Operation, Reading, Sent, TermRecord, Tree, View, ViewPiece, World } from '../types'

// scriptt in the app. The harness (.scriptt/harness.py in the folder of the session) does all the reading: it saves each
// reading to .scriptt/events.jsonl (form 5) and names its session in .scriptt/hooks.jsonl. This mod runs it on each message
// that you type, attaches its block for Claude, and hands the reading of your own message to hooks/row.tsx, which draws it
// on the message and lets you move its values. A drop there comes back here as a ui.message and goes to the engine as a
// correction through `harness.py post /accept` (what POST /accept of `harness.py serve` answers). The mod computes no meaning.
const PYTHONS = ['python3.14', '/opt/homebrew/bin/python3.14', '/usr/local/bin/python3.14']
const HARNESS = '.scriptt/harness.py'
// 1 colour for each type, in the order that the world and the message name the types. The status colours stay out of it.
const COLOURS = ['#5b9cf5', '#e5a33a', '#b07ee8', '#3fb8c4', '#ee78b0', '#8f9df7', '#c9b037', '#f08a4b', '#6cc4f0', '#c58fd8']

const readings = atom({ plugin: 'scriptt', key: 'readings' } as const, {}, { shape: 'readings-5' })
const mine = atom({ plugin: 'scriptt', key: 'mine' } as const, {}, { shape: 'mine-5' })
const said = atom({ plugin: 'scriptt', key: 'said' } as const, {})
const world = atom({ plugin: 'scriptt', key: 'world' } as const, { functions: {}, types: {} }, { shape: 'world-5' })
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

// The board of `harness.py serve`, open on 1 reading.
const BOARD = 'http://localhost:8787/'  // the desktop surface links http only to localhost; serve listens on 127.0.0.1

// The name of a type as agree.show writes it, from its tree.
const nameOf = (t: Tree): string =>
  typeof t.constructor === 'string' ? `${t.constructor}[${nameOf(t.of ?? ({} as Tree))}]` : (t.sum ?? t.brand ?? t.base ?? t.product ?? t.member ?? '')  // every object has a constructor: the tree's is a name
// The types of the values that a place of this type takes: the type, each alternative of a union at any depth, and the
// argument of Many, Maybe or Later. A union's name is the world's; its alternatives come from its tree.
const kindsOf = (name: string, w: World): string[] => {
  const inner = /^(?:Many|Maybe|Later)\[(.*)\]$/.exec(name)?.[1]
  if (inner) {
    return kindsOf(inner, w)
  }
  const walk = (t: Tree): string[] => [nameOf(t), ...(t.alternatives ?? []).filter(a => !a.member).flatMap(walk)]
  const tree = w.types[name]

  return [...new Set(name.split(' | ').flatMap(part => (w.types[part] ? walk(w.types[part] as Tree) : [part])).concat(tree ? walk(tree) : []))]
}
// The words of each member of a sum type of the world, by its type.
const membersOf = (w: World, name: string) => (w.types[name]?.alternatives ?? []).filter(a => a.member).map(a => a.words ?? '')

// A term as the row shows it in a hole: a value as its words, the result of operation n as #n, an absence as None, a hole as null.
const shown = (t: TermRecord | undefined): string | null => {
  if (!t || 'hole' in t) {
    return null
  }
  if ('constant' in t) {
    return String(t.constant)
  }
  if ('ref' in t) {
    return `#${t.ref}`
  }
  if ('function' in t) {
    return t.id === null ? t.function : `#${t.id}`
  }
  if ('several' in t) {
    return t.several.map(shown).join(', ')
  }

  return 'empty' in t ? 'None' : t.type
}

// The reading of 1 message as the row draws it: the engine's reading, with the user's changes over it until the engine takes them.
const viewOf = (r: Reading, own: Mine, saved: Record<string, boolean>, w: World): View => {
  const pieces: ViewPiece[] = r.constants
    .filter(c => c.at[0] >= 0)
    .map((c, id) => ({ id, start: c.at[0], end: c.at[1], type: c.type, value: String(c.constant), of: null }))
  const outcome = (id: string | null) => r.fulfillment?.find(one => String(one.obligation) === id)?.outcome ?? null
  const holeTypes = [...Object.values(w.functions).flatMap(f => f.parameters.map(([, t]) => nameOf(t))), ...r.phrases.flatMap(p => p.terms.flatMap(t => Object.values(t.parameters)))]
  const named = [...new Set([...holeTypes.flatMap(t => kindsOf(t, w)), ...pieces.map(p => p.type)])].filter(t => w.types[t] || pieces.some(p => p.type === t))
  const colours = Object.fromEntries(named.map((t, n) => [t, COLOURS[n % COLOURS.length] ?? 'text']))

  const parts = r.phrases.map((phrase, n) => {
    const yours = own[n]
    const demands = yours?.demands ?? phrase.terms.map(t => t.function)
    const things = yours?.things ?? {}
    const tag = phrase.quotes !== null ? 'quote' : [...phrase.terms.map(t => `#${t.id} ${t.function}${outcome(t.id) ? ` ${outcome(t.id)}` : ''}`), ...phrase.unresolved.map(u => `#${u.id} ?`)].join(' ') || 'nothing'

    const calls = demands.map(fn => {
      const term: Operation | undefined = phrase.terms.find(t => t.function === fn)
      const holes = Object.entries(term?.arguments ?? {}).map(([path, value]) => {
        const key = `${fn}.${path}`
        const said = key in things ? (things[key] ?? null) : shown(value)
        const at = value && 'at' in value ? value.at : null
        const piece = key in things ? pieces.find(p => p.value === said) : pieces.find(p => at && p.start === at[0] && p.end === at[1])

        return { path, type: term?.parameters[path] ?? '', value: said, piece: said === null ? null : (piece?.id ?? null) }
      })
      const hidden = Object.entries(term?.parameters ?? {}).filter(([path]) => !(path in (term?.arguments ?? {}))).map(([path, type]) => ({ path, type }))

      return { fn, holes, hidden, check: term ? outcome(term.id) : null }
    })

    // A phrase holds the white space after it: the tag goes after its last word.
    return { start: phrase.start, end: phrase.start + r.text.slice(phrase.start, phrase.end).trimEnd().length, tag: yours ? demands.join(' ') || 'nothing' : tag, demands, things, calls, said: saved[n] ?? null }
  })

  return {
    text: r.text,
    colours,
    kinds: Object.fromEntries([...new Set(holeTypes)].map(t => [t, kindsOf(t, w)])),
    parts,
    pieces,
    functions: Object.entries(w.functions).map(([name, f]) => ({ name, asks: f.asks })),
    types: named.map(name => ({ name, doc: '', members: membersOf(w, name) })),
  }
}

// The value of a change as a term record: a value of the message by its place, a member of the world by its type, the
// result of an operation by its number, or a cleared hole. null: the engine has no such value.
const valueOf = (said: string | null, place: string, r: Reading, w: World): TermRecord | null => {
  if (said === null) {
    return { hole: place, reason: 'cleared' }
  }
  if (/^#\d+$/.test(said)) {
    return { ref: said.slice(1) }
  }
  const given = r.constants.find(c => String(c.constant) === said)
  if (given) {
    return given
  }
  const sum = Object.keys(w.types).find(name => membersOf(w, name).includes(said))

  return sum ? { constant: said, type: sum, at: [-1, -1] } : null
}

// The latest snapshot of the reading that the harness made for this session, from its 2 files.
const latest = async ($: EngineInterface, id: string): Promise<Reading | undefined> => {
  const at = await home($)
  const sent: Sent[] = (await $.fs.read(`${at}/.scriptt/hooks.jsonl`)).trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
  const mine = [...sent].reverse().find(line => line.event === 'UserPromptSubmit' && line.session === id)
  const lines: Reading[] = (await $.fs.read(`${at}/.scriptt/events.jsonl`)).trim().split('\n').filter(Boolean).map(line => JSON.parse(line))

  return mine ? [...lines].reverse().find(line => line.id === mine.reading) : undefined
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
        const record = await latest($, id)

        if (!record) {
          throw new Error('the harness named no reading for this session')
        }

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

  // When Claude's turn ends, the Stop hook of the harness checks it from the transcript and saves the outcomes with the
  // reading. The mod runs no check of its own (it has no transcript): it reads the latest snapshot again.
  on('turn.complete', async ($, e, next) => {
    const id = await read($, session)
    const ended = await next(e)

    if (id && lastText) {
      try {
        const of = lastText
        const record = await latest($, id)
        record && (await update($, readings, all => ({ ...all, [of]: record })))
      } catch {
        // the outcomes are extra: a turn ends the same without them
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
    const { Link } = $.ui.resolve(e)
    const props = viewOf(reading, (await read($, mine))[text] ?? {}, (await read($, said))[text] ?? {}, await read($, world))

    return (
      <Box width="100%" flexDirection="column">
        <Client key="row" module="./row.tsx" width="100%" props={props} />
        <Link key="board" href={`${BOARD}?reading=${reading.id}`}>open the board for this message</Link>
      </Box>
    )
  })

  // A press or a drop in the row: the user's change of 1 or 2 parts. Each changed hole goes to the engine as a correction;
  // the row shows it at once. If the engine does not take one, that part goes back and the status line says why.
  on('ui.message', async ($, e, next) => {
    const data = (e.data ?? {}) as { text?: unknown; changes?: unknown }
    const text = typeof data.text === 'string' ? data.text : ''

    for (const raw of text && Array.isArray(data.changes) ? (data.changes as Partial<Change>[]) : []) {
      const reading = (await read($, readings))[text]
      const phrase = typeof raw.part === 'number' ? reading?.phrases[raw.part] : undefined

      if (!reading || !phrase || typeof raw.part !== 'number' || !Array.isArray(raw.demands) || typeof raw.things !== 'object') {
        continue
      }

      const part = raw.part
      const demands = raw.demands.filter(name => typeof name === 'string')
      const things = Object.fromEntries(Object.entries(raw.things ?? {}).filter(([, v]) => v === null || typeof v === 'string'))
      const was: { before?: Omit<Change, 'part'> } = {}

      await update($, mine, all => {
        was.before = all[text]?.[part]

        return { ...all, [text]: { ...(all[text] ?? {}), [part]: { demands, things } } }
      })

      let failed = ''
      let now = reading
      const w = await read($, world)

      try {
        if (demands.join(' ') !== phrase.terms.map(t => t.function).join(' ')) {
          throw new Error('adding or removing a function is not a correction the engine takes yet')
        }

        for (const [key, said] of Object.entries(things)) {
          const [fn = '', ...rest] = key.split('.')
          const path = rest.join('.')
          const term = phrase.terms.find(t => t.function === fn)
          const value = term ? valueOf(said, term.parameters[path] ?? '', now, w) : null

          if (!term || term.id === null || !value) {
            throw new Error(`no correction for ${key}`)
          }

          const ran = await harness($, ['post', '/accept'], { stdin: JSON.stringify({ reading: now.id, number: Number(term.id), path, value }) })
          const answer: Accepted = ran.exitCode === 0 ? JSON.parse(ran.stdout) : { saved: null, diagnostics: [], error: lastLine(ran.stderr) }

          if (!answer.saved) {
            throw new Error(answer.error || `the engine refused it: ${answer.diagnostics.map(d => d.filter(x => x !== null).join(' ')).join('; ')}`)
          }

          now = answer.saved
        }
      } catch (error) {
        failed = lastLine(reason(error))
      }

      now !== reading && (await update($, readings, all => ({ ...all, [text]: now })))

      if (failed) {
        await update($, mine, all => {
          const rest = { ...(all[text] ?? {}) }
          delete rest[part]

          return { ...all, [text]: was.before === undefined ? rest : { ...rest, [part]: was.before } }
        })
      }

      await update($, said, all => ({ ...all, [text]: { ...(all[text] ?? {}), [part]: !failed } }))
      $.ui.status(failed ? `${failed}: your change was not saved` : undefined)
    }

    return next(e)
  })

  on('ui.fault', async ($, e, next) => {
    fault = e.reason
    $.ui.status(`${e.reason}: the app draws the rows`)

    return next(e)
  })
}
