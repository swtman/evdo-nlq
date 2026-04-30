export type Provider = {
  id: string
  models: string[]
}

export type ParsedSSEEvent = {
  event: string
  data: string
}

export type QueryState =
  | { status: 'idle' }
  | { status: 'streaming'; sparql: string; columns?: string[]; rows?: Record<string, string>[] }
  | {
      status: 'done'
      sparql: string
      columns: string[]
      rows: Record<string, string>[]
      inputTokens: number
      outputTokens: number
      retries: number
    }
  | { status: 'error'; message: string }
