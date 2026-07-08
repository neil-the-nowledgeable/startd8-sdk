import { getBackendSrv } from '@grafana/runtime';

/**
 * POST through the Grafana datasource proxy. The bearer token is NEVER sent from the browser — the
 * proxy's secureJsonData holds it and adds it server-side (FR-2/S-3). The panel only knows the UID.
 */
export async function proxyPost<T>(dsUid: string, path: string, body: unknown): Promise<T> {
  return getBackendSrv().post(`/api/datasources/proxy/uid/${dsUid}/${path}`, body);
}

/** Best-effort human message from a Grafana backend error (covers both `error` and `refused_reason`). */
export function errText(err: unknown): string {
  if (err && typeof err === 'object') {
    const e = err as {
      data?: { error?: string; refused_reason?: string };
      statusText?: string;
      message?: string;
    };
    return e.data?.error || e.data?.refused_reason || e.message || e.statusText || 'request failed';
  }
  return String(err);
}
