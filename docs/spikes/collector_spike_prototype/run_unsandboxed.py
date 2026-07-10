"""Baseline (no sandbox): boot collector, measure boot->ready, emit spans,
measure convergence lag (span -> calls_total visible), scrape /metrics, memory.
"""
import subprocess, time, sys, urllib.request, os, signal

BIN = "/tmp/collector_spike/otelcol-contrib"
CFG = "/tmp/collector_spike/collector-config.yaml"
METRICS_URL = "http://127.0.0.1:8889/metrics"
PROM_PORT = 8889


def scrape():
    try:
        with urllib.request.urlopen(METRICS_URL, timeout=1.0) as r:
            return r.read().decode()
    except Exception:
        return None


def wait_ready(timeout=20.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        body = scrape()
        if body is not None:
            return time.monotonic() - start
        time.sleep(0.05)
    return None


def rss_mb(pid):
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) / 1024.0
    except Exception:
        return None


def main():
    t0 = time.monotonic()
    proc = subprocess.Popen([BIN, "--config", CFG],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)
    try:
        ready = wait_ready()
        if ready is None:
            print("COLLECTOR NEVER READY")
            print(proc.stdout.read()[:3000] if proc.stdout else "")
            return
        print(f"BOOT_TO_READY_S={ready:.3f}")
        boot_mem = rss_mb(proc.pid)
        print(f"BOOT_RSS_MB={boot_mem:.1f}" if boot_mem else "BOOT_RSS_MB=?")

        # Emit spans; record wall time of emission start.
        emit_start = time.monotonic()
        er = subprocess.run([sys.executable, "/tmp/collector_spike/emit_spans.py",
                             "checkoutservice", "8", "3"],
                            capture_output=True, text=True, timeout=60)
        print(er.stdout.strip())
        if er.returncode != 0:
            print("EMIT FAILED:", er.stderr[:2000])
            return

        # Poll /metrics until calls_total appears (convergence).
        conv = None
        conv_deadline = time.monotonic() + 15.0
        final_body = None
        while time.monotonic() < conv_deadline:
            body = scrape()
            if body and "calls_total" in body:
                conv = time.monotonic() - emit_start
                final_body = body
                break
            time.sleep(0.1)
        if conv is None:
            print("CONVERGENCE TIMEOUT — calls_total never appeared")
            final_body = scrape()
        else:
            print(f"CONVERGENCE_LAG_S={conv:.3f}  (emit-start -> calls_total visible)")

        run_mem = rss_mb(proc.pid)
        print(f"RUN_RSS_MB={run_mem:.1f}" if run_mem else "RUN_RSS_MB=?")

        # Print the RED surface lines.
        print("===METRICS_RED_SURFACE===")
        if final_body:
            for line in final_body.splitlines():
                if line.startswith("calls_total") or "duration_milliseconds" in line:
                    print(line)
        print("===END===")
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass


if __name__ == "__main__":
    main()
