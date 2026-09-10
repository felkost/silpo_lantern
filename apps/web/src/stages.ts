// G10 (A-G10-01): the io kind per graph node, mirroring NODE_IO in
// apps/api/routes.py -- each side names the other as its mirror, the
// convention replay.py already uses for TAPED_ERROR_KEY. The wire carries
// `io` too; this map only labels a kind the client has never seen.

export type IoKind = "mcp" | "llm" | "db" | "pure" | "mcp+db";

export const IO_LABEL: Record<IoKind, string> = {
  mcp: "MCP",
  llm: "LLM",
  db: "DB",
  pure: "pure",
  "mcp+db": "MCP + DB",
};

/** D90: cumulative spend for this session, from the provider's own usage
 * block. `ceiling_usd` is a project decision, never a remaining balance. */
export interface Spend {
  tokens: number;
  cost_usd: number;
  ceiling_usd: number;
}

export interface StageRow {
  node: string;
  io: IoKind;
  usage?: Spend;
}
