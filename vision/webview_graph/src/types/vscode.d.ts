interface VSCodeApi {
  postMessage(message: unknown): void
  getState(): unknown
  setState(state: unknown): unknown
}

declare function acquireVsCodeApi(): VSCodeApi