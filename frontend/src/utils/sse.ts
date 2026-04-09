/**
 * src/utils/sse.ts
 *
 * 轻量 SSE (Server-Sent Events) 工具，基于 fetch streaming。
 * 支持鉴权 header（浏览器原生 EventSource 不支持自定义 header）。
 *
 * 协议约定：
 *   每行格式：`data: <token>\n\n`
 *   结束标记：`data: [DONE]\n\n`
 *   错误事件：`event: error\ndata: <message>\n\n`
 */

export interface SSEOptions {
  /** HTTP method（默认 POST）*/
  method?: 'GET' | 'POST'
  /** 请求 body（POST 时）*/
  body?: object
  /** 额外 headers（e.g. Authorization）*/
  headers?: Record<string, string>
  /** 每收到一个 token 调用 */
  onToken: (token: string) => void
  /** 完成时调用（已收到 [DONE]）*/
  onDone?: () => void
  /** 错误时调用 */
  onError?: (message: string) => void
  /** AbortSignal（用于取消）*/
  signal?: AbortSignal
}

/**
 * 发起 SSE 请求，逐 token 回调。
 *
 * @param url  相对路径，自动加上 `/api` 前缀（若没有）
 */
export async function streamSSE(url: string, opts: SSEOptions): Promise<void> {
  const { method = 'POST', body, headers = {}, onToken, onDone, onError, signal } = opts

  // 从 localStorage 取 token（与 axios client 一致）
  const token = localStorage.getItem('access_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const fetchHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
    ...headers,
  }

  // 确保 URL 以 /api 开头
  const fullUrl = url.startsWith('/api') ? url : `/api${url.startsWith('/') ? url : `/${url}`}`

  let response: Response
  try {
    response = await fetch(fullUrl, {
      method,
      headers: fetchHeaders,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (e: any) {
    onError?.(e?.message ?? 'Network error')
    return
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const json = await response.json()
      detail = json?.detail ?? detail
    } catch {}
    onError?.(detail)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onError?.('No response body')
    return
  }

  const decoder = new TextDecoder()
  let buf = ''
  let errorSeen = false

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buf += decoder.decode(value, { stream: true })

      // 按 \n\n 分割 SSE 事件
      const events = buf.split('\n\n')
      // 最后一个可能不完整，留给下次拼接
      buf = events.pop() ?? ''

      for (const event of events) {
        const lines = event.split('\n')
        let eventType = 'message'
        let data = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice('event: '.length).trim()
          } else if (line.startsWith('data: ')) {
            data = line.slice('data: '.length)
          }
        }

        if (eventType === 'error') {
          errorSeen = true
          onError?.(data)
          break
        }

        if (data === '[DONE]') {
          onDone?.()
          return
        }

        if (data) {
          // 还原转义的换行符
          const token = data.replace(/\\n/g, '\n')
          onToken(token)
        }
      }

      if (errorSeen) break
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}
