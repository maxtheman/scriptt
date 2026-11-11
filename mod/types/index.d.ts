// What the mod keeps for the session. A Reading is the latest snapshot of 1 reading in .scriptt/events.jsonl (form 5), as
// scriptt16.record wrote it. Which reading belongs to which message of which session is in .scriptt/hooks.jsonl.

// A term as a record writes it: a value the message gives, the result of an earlier operation, an operation written in place,
// a record, a collection, a deliberate absence, or a hole with its reason.
export type TermRecord =
  | { constant: string | number; type: string; at: [number, number] }
  | { ref: string }
  | Operation
  | { fields: Record<string, TermRecord>; type: string }
  | { several: TermRecord[]; type: string }
  | { empty: string }
  | { hole: string; reason: string }
export type Operation = {
  id: string | null
  function: string
  type: string
  parameters: Record<string, string>
  arguments: Record<string, TermRecord>
  judgments?: { valid: boolean; diagnostics: string[][]; complete: boolean; pending: boolean; deferred: boolean; ready: boolean }
}
export type Phrase = {
  start: number
  end: number
  brand: string
  starts_by: string
  quotes: number | null
  terms: Operation[]
  unresolved: { id: string; reason: string; place: number }[]
}
// 1 outcome of the check at the end of a turn, for 1 obligation.
export type Checked = { obligation: number; criterion: string; outcome: 'PASS' | 'FAIL' | 'UNVERIFIED'; evidence: number | null; claim: number | null }
export type Reading = {
  form: 5
  id: string
  text: string
  world: string
  snapshot?: string
  phrases: Phrase[]
  constants: { constant: string | number; type: string; at: [number, number] }[]
  decisions: unknown[]
  corrections: { operation: number; path: string; status: string }[]
  fulfillment?: Checked[]
}
export type Readings = Record<string, Reading>
// 1 line of .scriptt/hooks.jsonl: the session that sent a reading.
export type Sent = { event: string; session: string | null; reading?: string }

// A type of the world as agree.tree writes it.
export type Tree = {
  sum?: string
  alternatives?: Tree[]
  member?: string
  words?: string
  base?: string
  brand?: string
  of?: Tree
  constructor?: string
  product?: string
  fields?: Record<string, Tree>
}
// `harness.py world`: agree.world_record.
export type World = {
  identity?: string
  types: Record<string, Tree & { kind?: string }>
  functions: Record<string, { asks: string; parameters: [string, Tree][]; result: Tree }>
}

// The user's change of 1 part, as the row posts it: the functions it asks for, and the holes the user filled or opened.
export type Change = { part: number; demands: string[]; things: Record<string, string | null> }
// For each part number: the user's last change of it.
export type Mine = Record<string, Omit<Change, 'part'>>
// For each part number: whether the engine took the user's last change of it.
export type Said = Record<string, boolean>
// What `harness.py post /accept` answers.
export type Accepted = { saved: Reading | null; diagnostics: (string | number | null)[][]; error?: string }

// What the row's surface module (hooks/row.tsx) draws: the props that the hooks module hands it.
// check: the outcome of the check at the end of the turn, or null before it.
export type ViewHole = { path: string; type: string; value: string | null; piece: number | null }
export type ViewCall = { fn: string; holes: ViewHole[]; hidden: { path: string; type: string }[]; check: string | null }
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
  // For each type that a hole can name: the types of the values it takes.
  kinds: Record<string, string[]>
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
      world: Shaped<World>
      session: string
      python: string
    }
  }
}
