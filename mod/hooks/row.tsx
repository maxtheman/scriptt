import type { ClientModule, ClientPointerEvent, ClientSurface } from 'claude-code'

import type { Change, View } from '../types'

// The row of 1 message, drawn by the surface: the message as typed, each piece of it in the colour of its type, and the tag
// of each part. "scriptt" turns on drag mode: the things that can move slant back and forth, each part shows its calls with
// their holes, and the world lies below the message. Every cell is 1 character of the code font, so a pointer event names
// the thing under it. Until the first pointer event, drag mode draws its things as buttons: press one, then press where it goes.
type Hit =
  | { kind: 'part'; part: number }
  | { kind: 'piece'; id: number }
  | { kind: 'fn'; part: number; fn: string }
  | { kind: 'hole'; part: number; fn: string; path: string }
  | { kind: 'world-fn'; fn: string }
  | { kind: 'world-type'; type: string }
  | { kind: 'member'; type: string; value: string }
type Look = 'word' | 'mark' | 'piece' | 'fn' | 'hole' | 'open' | 'tag' | 'type'
type Token = { text: string; key: string; hit: Hit | null; look: Look; type: string | null; part: number | null; lit: string[] }
type Cell = { x: number; token: Token }
type Held =
  | { what: 'fn'; fn: string; part: number | null; source: string }
  | { what: 'thing'; type: string; value: string; from: { part: number; key: string } | null; source: string }
  | { what: 'type'; type: string; source: string }
type S = {
  isDrag: boolean
  isPointer: boolean
  phase: number
  hover: string | null
  down: { token: Token; x: number; y: number } | null
  held: Held | null
  at: { x: number; y: number } | null
}

const START: S = { isDrag: false, isPointer: false, phase: 0, hover: null, down: null, held: null, at: null }
const INK = '#111111'
const drawn = new WeakMap<object, { view: View; rows: Cell[][] }>()
const started = new WeakSet<object>()

// A prop left undefined or false is left out: the surface draws its default.
const clean = (style: Record<string, unknown>) => Object.fromEntries(Object.entries(style).filter(([, v]) => v !== undefined && v !== false))
const accepts = (view: View, hole: string, type: string) => (view.kinds[hole] ?? hole.split('|').map(t => t.trim())).includes(type)

// The things in a part's calls: what a drag can pick there.
const pick = (token: Token, view: View): Held | null => {
  const hit = token.hit
  const source = token.key

  switch (hit?.kind) {
    case 'piece': {
      const piece = view.pieces.find(p => p.id === hit.id)
      return piece ? { what: 'thing', type: piece.type, value: piece.value, from: null, source } : null
    }
    case 'fn':
      return { what: 'fn', fn: hit.fn, part: hit.part, source }
    case 'hole': {
      const hole = view.parts[hit.part]?.calls.find(c => c.fn === hit.fn)?.holes.find(h => h.path === hit.path)
      return hole?.value == null ? null : { what: 'thing', type: hole.type, value: hole.value, from: { part: hit.part, key: `${hit.fn}.${hit.path}` }, source }
    }
    case 'world-fn':
      return { what: 'fn', fn: hit.fn, part: null, source }
    case 'world-type':
      return { what: 'type', type: hit.type, source }
    case 'member':
      return { what: 'thing', type: hit.type, value: hit.value, from: null, source }
    default:
      return null
  }
}

// What a drop of `held` on `hit` records: 1 reading for each part that changes. null: it cannot drop there.
const drop = (held: Held, hit: Hit | null, view: View): Change[] | null => {
  const changed = new Map<number, Change>()
  const at = (part: number) => {
    const now = view.parts[part]
    const change = changed.get(part) ?? { part, demands: [...(now?.demands ?? [])], things: { ...(now?.things ?? {}) } }
    changed.set(part, change)

    return change
  }
  const tray = hit?.kind === 'world-fn' || hit?.kind === 'world-type' || hit?.kind === 'member'
  const part = hit && 'part' in hit ? hit.part : hit?.kind === 'piece' ? view.parts.findIndex(p => p.start <= (view.pieces.find(x => x.id === hit.id)?.start ?? -1) && (view.pieces.find(x => x.id === hit.id)?.start ?? -1) < p.end) : -1
  // A hole of the function `fn` on the part that the world has and the part does not show yet: a drop there adds it.
  const hidden = (fn: string, type: string) => view.parts[part]?.calls.find(c => c.fn === fn)?.hidden.find(h => accepts(view, h.type, type))
  const remove = (from: number, fn: string) => {
    const change = at(from)
    change.demands = change.demands.filter(name => name !== fn)
    change.things = Object.fromEntries(Object.entries(change.things).filter(([key]) => !key.startsWith(`${fn}.`)))
  }

  if (held.what === 'fn' && part >= 0 && held.part !== part && !view.parts[part]?.demands.includes(held.fn)) {
    at(part).demands.push(held.fn)
    held.part === null || remove(held.part, held.fn)
  } else if (held.what === 'fn' && tray && held.part !== null) {
    remove(held.part, held.fn)
  } else if (held.what === 'thing' && hit?.kind === 'hole') {
    const hole = view.parts[hit.part]?.calls.find(c => c.fn === hit.fn)?.holes.find(h => h.path === hit.path)
    const key = `${hit.fn}.${hit.path}`

    if (!hole || !accepts(view, hole.type, held.type) || (held.from?.key === key && held.from.part === hit.part)) {
      return null
    }

    held.from && (at(held.from.part).things[held.from.key] = null)
    at(hit.part).things[key] = held.value
  } else if (held.what !== 'fn' && hit?.kind === 'fn' && hidden(hit.fn, held.type)) {
    held.what === 'thing' && held.from && (at(held.from.part).things[held.from.key] = null)
    at(hit.part).things[`${hit.fn}.${hidden(hit.fn, held.type)?.path}`] = held.what === 'thing' ? held.value : null
  } else if (held.what === 'thing' && tray && held.from) {
    at(held.from.part).things[held.from.key] = null
  } else {
    return null
  }

  return [...changed.values()]
}

// The address of a thing in the row: what a hover and a press name it by.
const keyOf = (hit: Hit) => Object.values(hit).join(':')

// The tokens of the row, in reading order. '\n' starts a row.
const tokensOf = (view: View, isDrag: boolean): Token[] => {
  const out: Token[] = []
  const number = new Map(view.pieces.map((p, n) => [p.id, n + 1]))
  // A piece has a number when a hole takes it or another piece stands for it: the hole and the other piece show the same number.
  const holes = view.parts.flatMap(p => p.calls.flatMap(c => c.holes.map(h => h.piece)))
  const mapped = new Set(view.pieces.filter(p => holes.includes(p.id) || p.of !== null || view.pieces.some(o => o.of === p.id)).map(p => p.id))
  const add = (text: string, look: Look, hit: Hit | null = null, type: string | null = null, part: number | null = null, lit: string[] = []) => {
    out.push({ text, key: hit ? keyOf(hit) : '', hit, look, type, part, lit })
  }
  const words = (from: number, to: number, part: number | null) => {
    for (const [unit] of view.text.slice(from, to).matchAll(/\n| +|[^ \n]+/g)) {
      add(unit, 'word', part === null || unit.trim() === '' ? null : { kind: 'part', part }, null, part)
    }
  }
  let cursor = 0

  view.parts.forEach((part, n) => {
    words(cursor, part.start, null)
    cursor = part.start

    for (const piece of view.pieces.filter(p => p.start >= part.start && p.start < part.end)) {
      words(cursor, piece.start, n)
      const lit = view.pieces.filter(p => p.of === piece.id || p.id === piece.of).map(p => keyOf({ kind: 'piece', id: p.id }))
      add(view.text.slice(piece.start, piece.end), 'piece', { kind: 'piece', id: piece.id }, piece.type, n, lit)
      isDrag && mapped.has(piece.id) && add(`#${number.get(piece.id)}${piece.of === null ? '' : `=#${number.get(piece.of) ?? ''}`}`, 'mark', null, null, n)
      cursor = piece.end
    }

    words(cursor, part.end, n)
    cursor = part.end
    add(' ', 'word', null, null, n)

    if (!isDrag || part.calls.length === 0) {
      add(part.tag, 'tag', isDrag ? { kind: 'part', part: n } : null, null, n)
    }

    for (const [c, call] of (isDrag ? part.calls : []).entries()) {
      c > 0 && add(' ', 'word', null, null, n)
      add(call.fn, 'fn', { kind: 'fn', part: n, fn: call.fn }, null, n)
      add('(', 'mark', null, null, n)
      call.holes.forEach((hole, h) => {
        h > 0 && add(', ', 'mark', null, null, n)
        add(`${hole.path}=`, 'mark', null, null, n)
        const lit = hole.piece === null ? [] : [keyOf({ kind: 'piece', id: hole.piece })]
        add(hole.value ?? hole.type, hole.value === null ? 'open' : 'hole', { kind: 'hole', part: n, fn: call.fn, path: hole.path }, hole.type, n, lit)
        hole.piece === null || add(`#${number.get(hole.piece)}`, 'mark', null, null, n)
      })
      add(')', 'mark', null, null, n)
    }
  })
  words(cursor, view.text.length, null)

  // The world, below the message: its functions, then 1 row for each type with members, then 1 row of the other types.
  if (isDrag) {
    add('\n', 'word')
    add('\n', 'word')
    view.functions.forEach((f, n) => (n > 0 && add(' ', 'word'), add(f.name, 'fn', { kind: 'world-fn', fn: f.name })))

    for (const type of view.types.filter(t => t.members.length > 0)) {
      add('\n', 'word')
      add(type.name, 'type', { kind: 'world-type', type: type.name }, type.name)
      type.members.forEach(value => (add(' ', 'word'), add(value, 'hole', { kind: 'member', type: type.name, value }, type.name)))
    }

    add('\n', 'word')
    view.types.filter(t => t.members.length === 0).forEach((t, n) => (n > 0 && add(' ', 'word'), add(t.name, 'type', { kind: 'world-type', type: t.name }, t.name)))
  }

  // A hovered hole or piece lights the pieces and holes that map to it.
  for (const token of out) {
    token.lit = [...new Set([token.key, ...token.lit, ...out.filter(o => o.lit.includes(token.key)).map(o => o.key)])].filter(Boolean)
  }

  return out
}

// Lays the tokens out in rows of at most `width` cells.
const rowsOf = (tokens: Token[], width: number): Cell[][] => {
  const rows: Cell[][] = [[]]
  let x = 0

  for (const token of tokens) {
    if (token.text === '\n' || (x > 0 && x + token.text.length > width)) {
      rows.push([])
      x = 0
    }

    if (token.text !== '\n' && !(x === 0 && token.text.trim() === '')) {
      rows[rows.length - 1]?.push({ x, token })
      x += token.text.length
    }
  }

  return rows
}

// A press, or a tap of the pointer: with nothing held it picks; with a thing held it drops, or picks another.
const tap = (token: Token | undefined, now: S, view: View, post: (data: { text: string; changes: Change[] }) => void): Partial<S> => {
  const changes = now.held && token ? drop(now.held, token.hit, view) : null

  if (!now.isDrag || !token || changes || now.held?.source === token.key) {
    changes && post({ text: view.text, changes })

    return { held: null, down: null }
  }

  return { held: pick(token, view) ?? now.held, down: null }
}

const Row: ClientModule<View, S> = (view, surface) => {
  const { Box, Text, Button } = surface.elements
  const s = surface.state ?? START
  const set = (next: Partial<S>) => surface.setState({ ...(surface.state ?? START), ...next })
  const tokens = tokensOf(view, s.isDrag)
  const rows = rowsOf(tokens, surface.columns || 80)
  drawn.set(surface, { view, rows })

  if (!started.has(surface)) {
    started.add(surface)
    surface.every(300, () => surface.state?.isDrag && set({ phase: 1 - surface.state.phase }))
    surface.onPointer((p: ClientPointerEvent) => {
      const now = { ...(surface.state ?? START), isPointer: true }
      const last = drawn.get(surface)
      const under = last?.rows[p.y]?.find(c => p.x >= c.x && p.x < c.x + c.token.text.length)?.token
      const hover = under?.key || null
      const isMoved = now.down !== null && (Math.abs(p.x - now.down.x) >= 1 || p.y !== now.down.y)

      if (p.type === 'down') {
        surface.setState({ ...now, hover, down: under && now.isDrag && last && pick(under, last.view) ? { token: under, x: p.x, y: p.y } : null })
      } else if (p.type === 'move' && now.down && !now.held && isMoved && last) {
        surface.setState({ ...now, hover, held: pick(now.down.token, last.view), at: { x: p.x, y: p.y } })
      } else if (p.type === 'up' && now.down && now.held && now.held.source === now.down.token.key) {
        const changes = drop(now.held, under?.hit ?? null, last?.view ?? view)
        changes && surface.post({ text: (last?.view ?? view).text, changes })
        surface.setState({ ...now, hover, held: null, down: null, at: null })
      } else if (p.type === 'up') {
        surface.setState({ ...now, hover, ...tap(under, now, last?.view ?? view, data => surface.post(data)), at: null })
      } else if (p.type === 'leave') {
        surface.setState({ ...now, hover: null })
      } else if (hover !== now.hover || now.held || !(surface.state?.isPointer ?? false)) {
        surface.setState({ ...now, hover, at: now.held ? { x: p.x, y: p.y } : null })
      }
    })
  }

  const hovered = tokens.find(t => t.key && t.key === s.hover)
  const lit = new Set(s.held ? [] : (hovered?.lit ?? []))
  const target = s.held && hovered ? drop(s.held, hovered.hit, view) : null
  const isTarget = (t: Token) => s.held !== null && t.hit !== null && drop(s.held, t.hit, view) !== null

  const styleOf = (t: Token, n: number) => clean(styleIn(t, n))
  const styleIn = (t: Token, n: number) => {
    const colour = t.type ? view.colours[t.type] : undefined
    const said = t.part === null ? null : (view.parts[t.part]?.said ?? null)
    const check = t.hit?.kind === 'fn' && t.part !== null ? view.parts[t.part]?.calls.find(c => c.fn === (t.hit as { fn: string }).fn)?.check : null
    const isMoving = s.isDrag && t.hit !== null && t.look !== 'word' && t.look !== 'tag' && t.look !== 'open'
    const base = {
      word: {},
      mark: { dimColor: true },
      piece: s.isDrag ? { backgroundColor: colour, color: INK } : { color: colour, underline: true },
      fn: { inverse: s.isDrag, weight: 'semibold' as const, dimColor: !s.isDrag },
      hole: { backgroundColor: colour, color: INK },
      open: { color: colour, italic: true, underline: true },
      tag: { dimColor: true, italic: s.isDrag },
      type: { color: colour, weight: 'semibold' as const },
    }[t.look]
    const status = t.look === 'fn' || t.look === 'tag' ? (said === true ? { color: 'success' } : said === false ? { color: 'error' } : {}) : {}

    return {
      ...base,
      ...status,
      ...(check != null && check === 'FAIL' ? { strikethrough: true } : {}),
      ...(isMoving && (n + s.phase) % 2 === 1 ? { italic: true } : {}),
      ...(lit.has(t.key) && t.look !== 'word' ? { weight: 'bold' as const, underline: true } : {}),
      ...(s.down?.token.key === t.key && !s.held ? { inverse: !('inverse' in base && base.inverse) } : {}),
      ...(s.held?.source === t.key ? { dimColor: true, inverse: false, backgroundColor: undefined, color: colour } : {}),
      ...(isTarget(t) ? { underline: true } : {}),
      ...(isTarget(t) && t.key === s.hover ? { inverse: true } : {}),
    }
  }

  const label = (held: Held) => (held.what === 'fn' ? held.fn : held.what === 'type' ? held.type : held.value)
  const heldType = s.held && s.held.what !== 'fn' ? s.held.type : null
  // The 1 line: what the drop under the pointer will record; with nothing held, the docstring of the world's thing under it.
  const line = target
    ? target.map(c => JSON.stringify(c)).join(' ')
    : !s.held && hovered?.hit?.kind === 'world-fn'
      ? (view.functions.find(f => f.name === (hovered.hit as { fn: string }).fn)?.asks ?? '')
      : !s.held && (hovered?.look === 'type' || hovered?.hit?.kind === 'member')
        ? (view.types.find(t => t.name === hovered.type)?.doc ?? '')
        : ''
  const isPress = s.isDrag && !s.isPointer

  return (
    <Box flexDirection="column">
      {isPress
        ? tokens
            .reduce<Token[][]>((lines, t) => (t.text === '\n' ? lines.push([]) : lines[lines.length - 1]?.push(t), lines), [[]])
            .map(line => (
              <Box flexDirection="row" flexWrap="wrap">
                {line.map((t, n) =>
                  t.hit && t.look !== 'word' ? (
                    <Button key={t.key} plain onPress={() => set(tap(t, surface.state ?? START, view, data => surface.post(data)))}>
                      <Text mono {...styleOf(t, n)}>{t.text}</Text>
                    </Button>
                  ) : (
                    <Text mono {...styleOf(t, n)}>{t.text}</Text>
                  ),
                )}
              </Box>
            ))
        : rows.map(row => (
            <Text mono wrap="truncate-end">
              {row.length === 0 ? ' ' : row.map((c, n) => <Text {...styleOf(c.token, n)}>{c.token.text}</Text>)}
            </Text>
          ))}
      {s.isDrag && (
        <Text mono dimColor wrap="truncate-end">
          {line || ' '}
        </Text>
      )}
      {s.held && s.at && (
        <Box position="absolute" top={s.at.y + 1} left={s.at.x}>
          <Text mono {...clean({ ...(heldType ? { backgroundColor: view.colours[heldType], color: INK } : { inverse: true }), ...(s.hover && !target ? { backgroundColor: 'error', color: INK } : {}) })}>
            {label(s.held)}
          </Text>
        </Box>
      )}
      <Box flexDirection="row">
        <Button key="scriptt" {...(s.isDrag ? { variant: 'primary' as const } : {})} onPress={() => set({ isDrag: !(surface.state ?? START).isDrag, held: null, down: null })}>
          scriptt
        </Button>
      </Box>
    </Box>
  )
}

export default Row
