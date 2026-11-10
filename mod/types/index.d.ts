// What the mod keeps for the session. A Reading is 1 line of .scriptt/events.jsonl for a message, as harness.py wrote it.
// Form 3 adds `choice` and `scores` to a part, `pieces`, and `piece` to a hole. A form 2 line has none of them: the mod derives them.
export type Hole = { type: string; value: string | null; by: string | null; piece?: number }
export type Demand = { function: string; p: number; by: string; part: number | null; parameters: Record<string, Hole>; python?: string; result?: string }
export type Part = { start: number; end: number; demands: string[]; hole: number | null; choice?: string; scores?: Record<string, number> }
export type Piece = {
  id: number
  part: number
  start: number
  end: number
  words: string
  type: string
  value: string
  by: string
  to: { demand: number; path: string } | null
  of: { piece: number; at?: string } | null
}
export type Reading = { text: string; session: string; parts: Part[]; demands: Demand[]; p: Record<string, number>; form?: number; pieces?: Piece[] }
export type Readings = Record<string, Reading>
// The user's reading of 1 part, as `harness.py reading` takes it: the functions it asks for, and the holes the user filled or opened.
export type Change = { part: number; demands: string[]; things: Record<string, string | null> }
// For each part number: the user's last reading of it.
export type Mine = Record<string, Omit<Change, 'part'>>
// For each message, d1's check of the reply against each function that the message asks for.
export type Checks = Record<string, number>
// For each part number: whether the log took the user's last reading of it.
export type Said = Record<string, boolean>
// `harness.py world`: each function with its docstring and holes, each type with its members (sum) or fields (product).
export type World = {
  functions: Record<string, { asks: string | null; returns: string; holes: Record<string, string> }>
  types: Record<string, { sum?: string[]; fields?: Record<string, string>; doc: string | null }>
}

// What the row's surface module (hooks/row.tsx) draws: the props that the hooks module hands it.
export type ViewHole = { path: string; type: string; value: string | null; piece: number | null }
export type ViewCall = { fn: string; holes: ViewHole[]; hidden: { path: string; type: string }[]; check: number | null }
export type ViewPart = {
  start: number
  end: number
  tag: string
  demands: string[]
  things: Record<string, string | null>
  calls: ViewCall[]
  said: boolean | null
}
export type ViewPiece = { id: number; start: number; end: number; type: string; value: string; of: number | null }
export type View = {
  text: string
  colours: Record<string, string>
  parts: ViewPart[]
  pieces: ViewPiece[]
  functions: { name: string; asks: string }[]
  types: { name: string; doc: string; members: string[] }[]
}

// python: the first interpreter that ran in this session. Empty: none tried yet.
declare module 'claude-code' {
  interface PluginState {
    scriptt: {
      readings: Shaped<Readings>
      mine: Shaped<Record<string, Mine>>
      said: Record<string, Said>
      checks: Record<string, Checks>
      world: Shaped<World>
      session: string
      python: string
    }
  }
}
