// What the mod keeps for the session. A Reading is 1 line of .scriptt/events.jsonl for a message, as harness.py wrote it.
export type Hole = { type: string; value: string | null; by: string | null }
export type Demand = { function: string; p: number; by: string; part: number | null; parameters: Record<string, Hole>; python?: string; result?: string }
export type Part = { start: number; end: number; demands: string[]; hole: number | null }
export type Reading = { text: string; session: string; parts: Part[]; demands: Demand[]; p: Record<string, number> }
export type Readings = Record<string, Reading>
// The user's own reading of a part: the functions that the part asks for. An empty list: the part asks for nothing.
export type Mine = Record<string, string[]>
// For each message, d1's check of the reply against each function that the message asks for.
export type Checks = Record<string, number>
// Each function of the world and its docstring: `functions[name].asks` of `harness.py world`.
export type World = Record<string, string>

// functions: the names alone, as the mod kept them before it kept the docstrings. Read only while world is empty.
// python: the first interpreter that ran in this session. Empty: none tried yet.
declare module 'claude-code' {
  interface PluginState {
    scriptt: {
      readings: Shaped<Readings>
      mine: Record<string, Mine>
      checks: Record<string, Checks>
      open: Record<string, boolean>
      functions: string[]
      world: World
      session: string
      python: string
    }
  }
}
