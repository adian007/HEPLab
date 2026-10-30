import { useEffect, useState } from 'react'
import { desktopRequest, isDesktop } from './desktop'

export type Overview = {
  name: string; version: string; stage: string; license: string; repository: string
  desktop_status: string
  capabilities: { id: string; name: string; status: string; detail: string; href: string }[]
  stack: { name: string; role: string }[]
  roadmap: { phase: string; name: string; status: string; detail: string }[]
}

export type Evidence = {
  silicon: {
    id: string; scope: string; source_url: string; source_sha256: string
    heldout_errors: { row: number; energy_gev: number; relative_error: number }[]
    max_abs_relative_error: number
    acceptance: { max_abs_relative_error: number; chosen_before_fit: boolean }
    status: string
  }
  cms_field: {
    model: string; reference_rows: number; tracker_rows: number
    max_vector_error_t: number; rms_vector_error_t: number; gate_max_vector_error_t: number
    passed: boolean; scope: string; full_map_transport: string
  }
}

export type Remote<T> = { state: 'loading' } | { state: 'ready'; data: T } | { state: 'offline' }

// Read-only project endpoints served by the local FastAPI app, or by the
// packaged worker inside the desktop shell. The site stays fully usable when
// they are unreachable (e.g. static hosting).
export function useRemote<T>(url: string): Remote<T> {
  const [value, setValue] = useState<Remote<T>>({ state: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    const request = isDesktop()
      ? desktopRequest<T>(url)
      : fetch(url, { headers: { Accept: 'application/json' }, signal: controller.signal })
          .then(response => { if (!response.ok) throw new Error(String(response.status)); return response.json() as Promise<T> })
    request
      .then(data => setValue({ state: 'ready', data }))
      .catch(error => { if (!controller.signal.aborted) { console.debug(`${url} unavailable`, error); setValue({ state: 'offline' }) } })
    return () => controller.abort()
  }, [url])
  return value
}
