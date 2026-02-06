#!/usr/bin/env python3
"""Load test pour le serveur MCP Proxmox (transport stdio).

Spawne N processus MCP en parallele, envoie des requetes JSON-RPC
via stdin/stdout, mesure les latences et genere un rapport.

Usage:
    python tests/load_test_mcp.py                    # standard (5 workers, 50 req)
    python tests/load_test_mcp.py --quick             # rapide (2 workers, 10 req)
    python tests/load_test_mcp.py --stress            # stress (10 workers, 200 req)
    python tests/load_test_mcp.py --workers 8 --requests 100
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# S'assurer que le projet est dans le path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ============================================================
# Configuration
# ============================================================

PROFILES = {
    "quick": {"workers": 2, "requests_per_worker": 5, "description": "Rapide"},
    "standard": {"workers": 5, "requests_per_worker": 10, "description": "Standard"},
    "stress": {"workers": 10, "requests_per_worker": 20, "description": "Stress"},
    "soak": {"workers": 3, "requests_per_worker": 50, "description": "Endurance"},
}

THRESHOLDS = {
    "initialize": {"p50": 500, "p95": 2000, "p99": 5000},
    "tools/list": {"p50": 100, "p95": 500, "p99": 1000},
    "tools/call": {"p50": 1000, "p95": 3000, "p99": 8000},
    "error_rate_warning": 0.01,
    "error_rate_critical": 0.05,
}

# Tools MCP a tester (du plus leger au plus lourd)
# On evite les tools destructifs et ceux qui appellent des API externes
TEST_SCENARIOS = [
    {"method": "tools/list", "params": {}},
    {"method": "tools/call", "params": {"name": "list_nodes", "arguments": {}}},
    {"method": "tools/call", "params": {"name": "list_vms", "arguments": {}}},
    {"method": "tools/call", "params": {"name": "list_containers", "arguments": {}}},
    {"method": "tools/call", "params": {"name": "list_users", "arguments": {}}},
]


# ============================================================
# Data classes
# ============================================================


@dataclass
class RequestResult:
    method: str
    tool_name: str | None
    latency_ms: float
    success: bool
    error: str | None = None
    response_size: int = 0


@dataclass
class WorkerResult:
    worker_id: int
    spawn_time_ms: float
    init_time_ms: float
    requests: list[RequestResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class Anomaly:
    severity: str  # CRITICAL, WARNING
    endpoint: str
    message: str
    recommendation: str


# ============================================================
# MCP stdio client
# ============================================================


class MCPStdioClient:
    """Client JSON-RPC pour communiquer avec le serveur MCP via stdio."""

    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self.process: asyncio.subprocess.Process | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    async def start(self) -> float:
        """Lance le processus MCP server. Retourne le temps de spawn en ms."""
        t0 = time.perf_counter()

        env = os.environ.copy()
        # Charger .env si present
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()

        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "proxmox_mcp.server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=env,
        )

        spawn_ms = (time.perf_counter() - t0) * 1000

        # Lancer le reader en background
        self._reader_task = asyncio.create_task(self._read_responses())

        return spawn_ms

    async def _read_responses(self):
        """Lit les reponses JSON-RPC depuis stdout du process."""
        assert self.process and self.process.stdout
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    self._pending[msg_id].set_result(msg)
        except (asyncio.CancelledError, ConnectionError):
            pass

    async def send_request(self, method: str, params: dict | None = None,
                           timeout: float = 30.0) -> tuple[dict, float]:
        """Envoie une requete JSON-RPC et attend la reponse.

        Returns:
            (response_dict, latency_ms)
        """
        self._msg_id += 1
        msg_id = self._msg_id

        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        assert self.process and self.process.stdin
        line = json.dumps(request) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            latency_ms = (time.perf_counter() - t0) * 1000
        except asyncio.TimeoutError:
            del self._pending[msg_id]
            raise
        finally:
            self._pending.pop(msg_id, None)

        return response, latency_ms

    async def send_notification(self, method: str, params: dict | None = None):
        """Envoie une notification JSON-RPC (pas de reponse attendue)."""
        notification: dict = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        assert self.process and self.process.stdin
        line = json.dumps(notification) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def initialize(self) -> float:
        """Handshake MCP. Retourne la latence en ms."""
        response, latency = await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "load-test", "version": "1.0.0"},
        })

        # Envoyer la notification initialized
        await self.send_notification("notifications/initialized")

        return latency

    async def close(self):
        """Ferme proprement le processus."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self.process:
            if self.process.stdin:
                try:
                    self.process.stdin.close()
                except Exception:
                    pass
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                self.process.kill()


# ============================================================
# Worker logic
# ============================================================


async def run_worker(
    worker_id: int,
    requests_per_worker: int,
    scenarios: list[dict],
) -> WorkerResult:
    """Execute un worker de load test complet."""
    result = WorkerResult(worker_id=worker_id, spawn_time_ms=0, init_time_ms=0)
    client = MCPStdioClient(worker_id)

    try:
        # 1. Spawn du process
        result.spawn_time_ms = await client.start()

        # 2. Initialize handshake
        t0 = time.perf_counter()
        result.init_time_ms = await client.initialize()

        # 3. Envoyer les requetes
        for i in range(requests_per_worker):
            scenario = scenarios[i % len(scenarios)]
            method = scenario["method"]
            params = scenario["params"]
            tool_name = params.get("name") if method == "tools/call" else None
            display_name = tool_name or method

            try:
                response, latency = await client.send_request(method, params, timeout=30.0)

                has_error = "error" in response
                error_msg = None
                if has_error:
                    error_msg = str(response["error"])

                result.requests.append(RequestResult(
                    method=method,
                    tool_name=tool_name,
                    latency_ms=latency,
                    success=not has_error,
                    error=error_msg,
                    response_size=len(json.dumps(response)),
                ))

            except asyncio.TimeoutError:
                result.requests.append(RequestResult(
                    method=method,
                    tool_name=tool_name,
                    latency_ms=30000,
                    success=False,
                    error="TIMEOUT (30s)",
                ))
            except Exception as e:
                result.requests.append(RequestResult(
                    method=method,
                    tool_name=tool_name,
                    latency_ms=0,
                    success=False,
                    error=str(e),
                ))

    except Exception as e:
        result.error = str(e)
    finally:
        await client.close()

    return result


# ============================================================
# Percentile helpers
# ============================================================


def percentile(data: list[float], p: float) -> float:
    """Calcule un percentile."""
    if not data:
        return 0
    k = (len(data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(data):
        return data[-1]
    d = k - f
    return data[f] + d * (data[c] - data[f])


def compute_metrics(latencies: list[float]) -> dict:
    """Calcule p50, p95, p99, avg, min, max."""
    if not latencies:
        return {"p50": 0, "p95": 0, "p99": 0, "avg": 0, "min": 0, "max": 0}
    s = sorted(latencies)
    return {
        "p50": percentile(s, 50),
        "p95": percentile(s, 95),
        "p99": percentile(s, 99),
        "avg": statistics.mean(s),
        "min": min(s),
        "max": max(s),
    }


# ============================================================
# Analysis & reporting
# ============================================================


def detect_anomalies(
    endpoint_metrics: dict[str, dict],
    endpoint_errors: dict[str, tuple[int, int]],
) -> list[Anomaly]:
    """Detecte les anomalies par rapport aux seuils."""
    anomalies = []

    for endpoint, metrics in endpoint_metrics.items():
        # Determiner le type de seuil
        if endpoint == "tools/list":
            thresholds = THRESHOLDS["tools/list"]
        elif endpoint.startswith("tools/call"):
            thresholds = THRESHOLDS["tools/call"]
        else:
            thresholds = THRESHOLDS.get(endpoint, THRESHOLDS["tools/call"])

        # Latence p95
        if metrics["p95"] > thresholds["p99"]:
            anomalies.append(Anomaly(
                severity="CRITICAL",
                endpoint=endpoint,
                message=f"p95={metrics['p95']:.0f}ms depasse le seuil p99={thresholds['p99']}ms",
                recommendation="Verifier la connexion Proxmox, la charge du serveur, ou le reseau",
            ))
        elif metrics["p95"] > thresholds["p95"]:
            anomalies.append(Anomaly(
                severity="WARNING",
                endpoint=endpoint,
                message=f"p95={metrics['p95']:.0f}ms depasse le seuil p95={thresholds['p95']}ms",
                recommendation="Surveiller la latence, optimiser si necessaire",
            ))

        # Latence p50
        if metrics["p50"] > thresholds["p50"]:
            anomalies.append(Anomaly(
                severity="WARNING",
                endpoint=endpoint,
                message=f"p50={metrics['p50']:.0f}ms depasse le seuil median={thresholds['p50']}ms",
                recommendation="Latence mediane elevee, verifier la charge de base",
            ))

        # Degradation ratio p99/p50
        if metrics["p50"] > 0 and metrics["p99"] / metrics["p50"] > 10:
            anomalies.append(Anomaly(
                severity="WARNING",
                endpoint=endpoint,
                message=f"Ratio p99/p50 = {metrics['p99']/metrics['p50']:.1f}x (seuil: 10x)",
                recommendation="Forte variance de latence, possible contention",
            ))

        # Taux d'erreur
        total, errors = endpoint_errors.get(endpoint, (0, 0))
        if total > 0:
            rate = errors / total
            if rate > THRESHOLDS["error_rate_critical"]:
                anomalies.append(Anomaly(
                    severity="CRITICAL",
                    endpoint=endpoint,
                    message=f"Taux d'erreur {rate:.1%} depasse le seuil critique "
                            f"{THRESHOLDS['error_rate_critical']:.0%}",
                    recommendation="Verifier les logs du serveur MCP et la connectivite Proxmox",
                ))
            elif rate > THRESHOLDS["error_rate_warning"]:
                anomalies.append(Anomaly(
                    severity="WARNING",
                    endpoint=endpoint,
                    message=f"Taux d'erreur {rate:.1%} depasse le seuil warning "
                            f"{THRESHOLDS['error_rate_warning']:.0%}",
                    recommendation="Surveiller les erreurs",
                ))

        # Timeout
        if metrics["max"] > 30000:
            anomalies.append(Anomaly(
                severity="CRITICAL",
                endpoint=endpoint,
                message=f"Timeout detecte (max={metrics['max']:.0f}ms > 30000ms)",
                recommendation="Verifier la connectivite Proxmox ou augmenter les timeouts",
            ))

    return anomalies


def status_label(metrics: dict, threshold_key: str) -> str:
    """Retourne OK / WARN / CRIT selon les metriques."""
    thresholds = THRESHOLDS.get(threshold_key, THRESHOLDS["tools/call"])
    if metrics["p95"] > thresholds["p99"]:
        return "CRIT"
    if metrics["p95"] > thresholds["p95"]:
        return "WARN"
    return " OK "


def generate_report(
    profile_name: str,
    num_workers: int,
    requests_per_worker: int,
    worker_results: list[WorkerResult],
    duration_s: float,
) -> str:
    """Genere le rapport de load test."""
    lines = []

    # Agglomerer toutes les requetes
    all_requests: list[RequestResult] = []
    spawn_times: list[float] = []
    init_times: list[float] = []
    worker_errors: list[str] = []

    for wr in worker_results:
        spawn_times.append(wr.spawn_time_ms)
        init_times.append(wr.init_time_ms)
        all_requests.extend(wr.requests)
        if wr.error:
            worker_errors.append(f"Worker {wr.worker_id}: {wr.error}")

    total_requests = len(all_requests)
    total_failures = sum(1 for r in all_requests if not r.success)
    error_rate = total_failures / total_requests if total_requests > 0 else 0
    all_latencies = [r.latency_ms for r in all_requests if r.success]
    rps = total_requests / duration_s if duration_s > 0 else 0

    # Grouper par endpoint
    endpoints: dict[str, list[RequestResult]] = {}
    for r in all_requests:
        key = r.tool_name or r.method
        endpoints.setdefault(key, []).append(r)

    # Metriques par endpoint
    endpoint_metrics: dict[str, dict] = {}
    endpoint_errors: dict[str, tuple[int, int]] = {}
    for ep, reqs in endpoints.items():
        latencies = [r.latency_ms for r in reqs if r.success]
        endpoint_metrics[ep] = compute_metrics(latencies)
        total = len(reqs)
        errs = sum(1 for r in reqs if not r.success)
        endpoint_errors[ep] = (total, errs)

    # Anomalies
    anomalies = detect_anomalies(endpoint_metrics, endpoint_errors)

    # === Rapport ===
    now = time.strftime("%Y-%m-%d %H:%M")
    lines.append("=" * 64)
    lines.append("   MCP PROXMOX - LOAD TEST REPORT (stdio)")
    lines.append(f"   Date: {now}")
    lines.append(f"   Profil: {profile_name}")
    lines.append(f"   Workers: {num_workers} | Req/worker: {requests_per_worker}"
                 f" | Duree: {duration_s:.1f}s")
    lines.append("=" * 64)

    # Resume
    lines.append("")
    lines.append("## Resume Executif")
    lines.append(f"  Total Requests:    {total_requests}")
    lines.append(f"  Total Failures:    {total_failures} ({error_rate:.2%})")
    if all_latencies:
        lines.append(f"  Avg Response Time: {statistics.mean(all_latencies):.0f}ms")
    lines.append(f"  RPS:               {rps:.1f}")
    lines.append(f"  Workers OK:        {sum(1 for w in worker_results if not w.error)}"
                 f"/{num_workers}")
    if worker_errors:
        lines.append(f"  Worker errors:     {len(worker_errors)}")

    # Spawn & Init
    lines.append("")
    lines.append("## Process Lifecycle")
    spawn_m = compute_metrics(spawn_times)
    init_m = compute_metrics(init_times)
    lines.append(f"  Spawn  - p50: {spawn_m['p50']:.0f}ms | "
                 f"p95: {spawn_m['p95']:.0f}ms | "
                 f"p99: {spawn_m['p99']:.0f}ms")
    lines.append(f"  Init   - p50: {init_m['p50']:.0f}ms | "
                 f"p95: {init_m['p95']:.0f}ms | "
                 f"p99: {init_m['p99']:.0f}ms")

    # Metriques par endpoint
    lines.append("")
    lines.append("## Metriques par Endpoint")
    lines.append("")
    header = (
        f"{'Endpoint':<25} {'Reqs':>5} {'Errs':>8} "
        f"{'p50':>8} {'p95':>8} {'p99':>8} {'Max':>8} {'Status':>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for ep in sorted(endpoints.keys()):
        m = endpoint_metrics[ep]
        total, errs = endpoint_errors[ep]
        err_pct = f"{errs} ({errs/total:.0%})" if total > 0 else "0 (0%)"
        tkey = "tools/list" if ep == "tools/list" else "tools/call"
        st = status_label(m, tkey)
        lines.append(
            f"{ep:<25} {total:>5} {err_pct:>8} "
            f"{m['p50']:>7.0f}ms {m['p95']:>6.0f}ms {m['p99']:>6.0f}ms "
            f"{m['max']:>6.0f}ms {st:>6}"
        )

    # Anomalies
    lines.append("")
    lines.append("## Anomalies Detectees")
    critical = [a for a in anomalies if a.severity == "CRITICAL"]
    warnings = [a for a in anomalies if a.severity == "WARNING"]

    if not anomalies:
        lines.append("  Aucune anomalie detectee.")
    else:
        if critical:
            lines.append("")
            lines.append("### CRITICAL")
            for a in critical:
                lines.append(f"  - [{a.endpoint}] {a.message}")
                lines.append(f"    Recommandation: {a.recommendation}")
        if warnings:
            lines.append("")
            lines.append("### WARNING")
            for a in warnings:
                lines.append(f"  - [{a.endpoint}] {a.message}")
                lines.append(f"    Recommandation: {a.recommendation}")

    # Worker errors
    if worker_errors:
        lines.append("")
        lines.append("## Erreurs Workers")
        for e in worker_errors:
            lines.append(f"  - {e}")

    # Erreurs de requetes
    unique_errors: dict[str, int] = {}
    for r in all_requests:
        if not r.success and r.error:
            key = f"[{r.tool_name or r.method}] {r.error[:100]}"
            unique_errors[key] = unique_errors.get(key, 0) + 1
    if unique_errors:
        lines.append("")
        lines.append("## Erreurs de Requetes")
        for err, count in sorted(unique_errors.items(), key=lambda x: -x[1]):
            lines.append(f"  - ({count}x) {err}")

    # Recommandations
    lines.append("")
    lines.append("## Recommandations")
    if not anomalies and error_rate == 0:
        lines.append("  1. Tous les tests passent - le serveur MCP est stable")
        lines.append("  2. Envisager un test stress (--stress) pour trouver les limites")
    elif critical:
        lines.append("  1. URGENT: Resoudre les problemes critiques ci-dessus")
        lines.append("  2. Verifier la connectivite Proxmox et les credentials")
        lines.append("  3. Relancer avec --quick pour isoler le probleme")
    else:
        lines.append("  1. Surveiller les warnings ci-dessus")
        lines.append("  2. Envisager un test d'endurance (--soak) pour confirmer la stabilite")

    lines.append("")
    lines.append("=" * 64)

    return "\n".join(lines)


# ============================================================
# Main
# ============================================================


async def run_load_test(
    profile_name: str,
    num_workers: int,
    requests_per_worker: int,
):
    """Execute le load test complet."""
    total_reqs = num_workers * requests_per_worker
    print("=" * 64)
    print(f"  MCP Proxmox Load Test - Profil: {profile_name}")
    print(f"  Workers: {num_workers} | Requests/worker: {requests_per_worker}"
          f" | Total: {total_reqs}")
    print("=" * 64)
    print()

    # Lancer tous les workers en parallele
    print(f"[+] Lancement de {num_workers} workers...")
    t0 = time.perf_counter()

    tasks = [
        run_worker(i, requests_per_worker, TEST_SCENARIOS)
        for i in range(num_workers)
    ]
    worker_results = await asyncio.gather(*tasks)

    duration_s = time.perf_counter() - t0
    print(f"[+] Termine en {duration_s:.1f}s")
    print()

    # Generer le rapport
    report = generate_report(
        profile_name=profile_name,
        num_workers=num_workers,
        requests_per_worker=requests_per_worker,
        worker_results=list(worker_results),
        duration_s=duration_s,
    )

    print(report)

    # Sauvegarder le rapport
    reports_dir = PROJECT_ROOT / "reports" / "load-tests"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"mcp_load_test_{timestamp}.txt"
    report_file.write_text(report)
    print(f"\nRapport sauvegarde: {report_file}")

    # Return code non-zero si anomalies critiques
    anomalies = detect_anomalies(
        {ep: compute_metrics([r.latency_ms for r in reqs if r.success])
         for ep, reqs in _group_requests(list(worker_results)).items()},
        {ep: (len(reqs), sum(1 for r in reqs if not r.success))
         for ep, reqs in _group_requests(list(worker_results)).items()},
    )
    return 1 if any(a.severity == "CRITICAL" for a in anomalies) else 0


def _group_requests(results: list[WorkerResult]) -> dict[str, list[RequestResult]]:
    """Groupe les requetes par endpoint."""
    groups: dict[str, list[RequestResult]] = {}
    for wr in results:
        for r in wr.requests:
            key = r.tool_name or r.method
            groups.setdefault(key, []).append(r)
    return groups


def main():
    parser = argparse.ArgumentParser(description="MCP Proxmox Load Test (stdio)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quick", action="store_true", help="Test rapide (2 workers, 5 req)")
    group.add_argument("--standard", action="store_true",
                       help="Test standard (5 workers, 10 req)")
    group.add_argument("--stress", action="store_true",
                       help="Test stress (10 workers, 20 req)")
    group.add_argument("--soak", action="store_true",
                       help="Test endurance (3 workers, 50 req)")
    parser.add_argument("--workers", type=int, help="Nombre de workers (override le profil)")
    parser.add_argument("--requests", type=int,
                        help="Requetes par worker (override le profil)")

    args = parser.parse_args()

    # Determiner le profil
    if args.quick:
        profile_name = "quick"
    elif args.stress:
        profile_name = "stress"
    elif args.soak:
        profile_name = "soak"
    else:
        profile_name = "standard"

    profile = PROFILES[profile_name]
    num_workers = args.workers or profile["workers"]
    requests_per_worker = args.requests or profile["requests_per_worker"]

    exit_code = asyncio.run(run_load_test(profile_name, num_workers, requests_per_worker))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
