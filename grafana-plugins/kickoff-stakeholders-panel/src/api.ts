import { getBackendSrv } from '@grafana/runtime';

/**
 * A fresh replay nonce per request. The endpoint's strict mode (mandatory when the apply gate is
 * enabled) requires a single-use `X-Nonce`; the server skips it when not strict, so sending it always
 * is harmless. Uniqueness — not cryptographic strength — is what the replay-nonce needs, and the
 * proxy forwards the browser-set nonce upstream (the token is added server-side, the nonce here).
 */
function newNonce(): string {
  return `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * POST through the Grafana datasource proxy. The bearer token is NEVER sent from the browser — the
 * proxy's secureJsonData holds it and adds it server-side (FR-2/S-3). The panel only knows the UID.
 * A fresh `X-Nonce` rides each request so a strict endpoint accepts it through the proxy.
 */
export async function proxyPost<T>(dsUid: string, path: string, body: unknown): Promise<T> {
  return getBackendSrv().post(`/api/datasources/proxy/uid/${dsUid}/${path}`, body, {
    headers: { 'X-Nonce': newNonce() },
  });
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
