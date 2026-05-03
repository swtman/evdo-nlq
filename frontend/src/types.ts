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
  | {
      status: 'streaming'
      sparql: string
      /** True between sparql_complete and results — GraphDB is running the query. */
      executing?: boolean
      columns?: string[]
      rows?: Record<string, string | undefined>[]
    }
  | {
      status: 'done'
      sparql: string
      columns: string[]
      rows: Record<string, string | undefined>[]
      inputTokens: number
      outputTokens: number
      retries: number
    }
  | {
      status: 'error'
      message: string
      /** SPARQL that was generated before the error, if any. */
      sparql?: string
    }
