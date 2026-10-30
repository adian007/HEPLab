// Desktop transport. Inside the Tauri shell the CSP blocks fetch('/api/...');
// requests go through the shell's single validated command to the packaged
// worker instead. In a browser this module is inert.

type TauriInternals = { invoke: <T>(command: string, args: Record<string, unknown>) => Promise<T> }

type DesktopError = { code: string; message: string }

// Web endpoints with an equivalent desktop operation (src/heplab/desktop/operations.json).
const OPERATIONS: Record<string, string> = {
  '/api/v1/project/overview': 'project.overview',
  '/api/v1/project/evidence': 'project.evidence',
  '/api/v1/detector': 'detector.geometry',
  '/api/v1/calibration': 'calibration.report',
  '/api/v1/datasets': 'datasets.list',
  '/api/v1/runs': 'runs.list',
}

function internals(): TauriInternals | undefined {
  return (window as unknown as { __TAURI_INTERNALS__?: TauriInternals }).__TAURI_INTERNALS__
}

export function isDesktop(): boolean {
  return internals() !== undefined
}

export function desktopOperation(url: string): string | undefined {
  return OPERATIONS[url]
}

// Resolves with the same JSON body the web endpoint returns; rejects for
// unmapped endpoints and for worker errors, so callers fall back to 'offline'.
export async function desktopRequest<T>(url: string): Promise<T> {
  const tauri = internals()
  const op = desktopOperation(url)
  if (!tauri) throw new Error('not running in the desktop shell')
  if (!op) throw new Error(`${url} has no desktop operation`)
  try {
    return await tauri.invoke<T>('heplab_invoke', { op, args: {} })
  } catch (error) {
    const detail = error as Partial<DesktopError>
    throw new Error(detail.code ? `${detail.code}: ${detail.message}` : String(error))
  }
}
