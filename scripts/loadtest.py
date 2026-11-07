#!/usr/bin/env python3
"""Performance e stress test do gateway. Somente leitura.

O painel fala só com o gateway (:8000). O script faz o mesmo caminho: login de
dev e os GETs das telas (títulos, pagamentos, exceções, conversas, aprovações,
configurações e métricas), mais /health e /me.

Não confirma exceção, não importa arquivo e não chama webhook. Worker, régua
e LLM ficam fora da carga. As rotas do painel passam pelo gateway e seguem
para cobrança, conciliação e cadastro — os três processos precisam estar no ar.

Requer a API no ar e o tenant demo:

    cd api && source .venv/bin/activate
    python -m app.cli seed-demo
    python ../scripts/loadtest.py perf
    python ../scripts/loadtest.py stress

`perf` mede latência e vazão com concorrência fixa.
`stress` sobe a concorrência em degraus até a taxa de erro ou o p95 passar
do limite e imprime o último degrau saudável.

Alvo que não seja local exige --allow-remote.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

try:
    import httpx
except ImportError:  # --help funciona sem o venv; a carga em si não.
    httpx = None  # type: ignore[assignment]


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


@dataclass(frozen=True, slots=True)
class Route:
    name: str
    path: str
    auth: bool

    @property
    def label(self) -> str:
        return f"GET {self.path.split('?', 1)[0]}"


# Mesmas leituras do painel. O peso é igual de propósito: a tabela por rota
# separa o /health barato do /metrics, que agrega o período no Postgres.
ROUTES: tuple[Route, ...] = (
    Route("health", "/health", auth=False),
    Route("me", "/me", auth=True),
    Route("invoices", "/invoices?limit=50", auth=True),
    Route("payments", "/payments?limit=50", auth=True),
    Route("exceptions", "/exceptions?limit=50", auth=True),
    Route("conversations", "/conversations?limit=50", auth=True),
    Route("approvals", "/approvals", auth=True),
    Route("settings", "/settings", auth=True),
    Route("metrics", "/metrics", auth=True),
)


@dataclass(slots=True)
class Sample:
    route: str
    status: int
    latency_ms: float
    error: str | None


@dataclass(slots=True)
class RouteSummary:
    route: str
    requests: int
    errors: int
    rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass(slots=True)
class Summary:
    concurrency: int
    duration_s: float
    requests: int
    errors: int
    rps: float
    min_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    routes: list[RouteSummary] = field(default_factory=list)
    error_kinds: dict[str, int] = field(default_factory=dict)

    @property
    def error_rate(self) -> float:
        if self.requests == 0:
            return 1.0
        return self.errors / self.requests


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * p
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


def summarize(samples: list[Sample], concurrency: int, duration_s: float) -> Summary:
    duration_s = max(duration_s, 1e-9)
    latencies = sorted(sample.latency_ms for sample in samples)
    errors = [sample for sample in samples if sample.error]
    kinds: dict[str, int] = defaultdict(int)
    for sample in errors:
        kinds[sample.error or "erro"] += 1

    by_route: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_route[sample.route].append(sample)

    routes: list[RouteSummary] = []
    for name in sorted(by_route):
        group = by_route[name]
        group_lat = sorted(item.latency_ms for item in group)
        routes.append(
            RouteSummary(
                route=name,
                requests=len(group),
                errors=sum(1 for item in group if item.error),
                rps=len(group) / duration_s,
                p50_ms=percentile(group_lat, 0.50),
                p95_ms=percentile(group_lat, 0.95),
                p99_ms=percentile(group_lat, 0.99),
            )
        )

    total = len(samples)
    return Summary(
        concurrency=concurrency,
        duration_s=duration_s,
        requests=total,
        errors=len(errors),
        rps=total / duration_s,
        min_ms=latencies[0] if latencies else 0.0,
        p50_ms=percentile(latencies, 0.50),
        p95_ms=percentile(latencies, 0.95),
        p99_ms=percentile(latencies, 0.99),
        max_ms=latencies[-1] if latencies else 0.0,
        mean_ms=(sum(latencies) / total) if total else 0.0,
        routes=routes,
        error_kinds=dict(kinds),
    )


def saturation_reason(summary: Summary, max_error_rate: float, max_p95_ms: float) -> str | None:
    if summary.requests == 0:
        return "nenhuma resposta"
    if summary.error_rate > max_error_rate:
        return f"erros {summary.error_rate:.2%} > {max_error_rate:.2%}"
    if summary.p95_ms > max_p95_ms:
        return f"p95 {summary.p95_ms:.0f}ms > {max_p95_ms:.0f}ms"
    return None


def assert_safe_target(base_url: str, allow_remote: bool) -> None:
    host = (urlparse(base_url).hostname or "").lower()
    local = host in LOCAL_HOSTS or host.endswith(".local")
    if local or allow_remote:
        return
    raise SystemExit(
        f"{host} não é um host local. Use --allow-remote só se o alvo for um ambiente de teste."
    )


def select_routes(raw: str | None) -> tuple[Route, ...]:
    if not raw:
        return ROUTES
    wanted = {name.strip() for name in raw.split(",") if name.strip()}
    known = {route.name for route in ROUTES}
    unknown = wanted - known
    if unknown:
        names = ", ".join(sorted(known))
        raise SystemExit(f"rota desconhecida: {', '.join(sorted(unknown))}. Opções: {names}")
    selected = tuple(route for route in ROUTES if route.name in wanted)
    if not selected:
        raise SystemExit("informe ao menos uma rota")
    return selected


async def one_request(client: httpx.AsyncClient, route: Route, token: str) -> Sample:
    headers = {"authorization": f"Bearer {token}"} if route.auth else {}
    started = time.perf_counter()
    try:
        response = await client.get(route.path, headers=headers)
        await response.aread()
        status = response.status_code
        error = None if 200 <= status < 300 else f"http_{status}"
    except httpx.TimeoutException:
        status, error = 0, "timeout"
    except httpx.HTTPError as exc:
        status, error = 0, type(exc).__name__
    return Sample(route.label, status, (time.perf_counter() - started) * 1000, error)


async def worker(
    client: httpx.AsyncClient,
    routes: tuple[Route, ...],
    token: str,
    stop: asyncio.Event,
    samples: list[Sample],
    index: int,
) -> None:
    cursor = index
    size = len(routes)
    while not stop.is_set():
        samples.append(await one_request(client, routes[cursor % size], token))
        cursor += size


async def run_stage(
    client: httpx.AsyncClient,
    routes: tuple[Route, ...],
    token: str,
    concurrency: int,
    duration: float,
) -> tuple[list[Sample], float]:
    stop = asyncio.Event()
    samples: list[Sample] = []
    started = time.perf_counter()
    tasks = [
        asyncio.create_task(worker(client, routes, token, stop, samples, index))
        for index in range(concurrency)
    ]
    await asyncio.sleep(duration)
    stop.set()
    await asyncio.gather(*tasks)
    return samples, time.perf_counter() - started


async def _service_title(client: httpx.AsyncClient) -> str | None:
    try:
        response = await client.get("/openapi.json")
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    title = (response.json().get("info") or {}).get("title")
    return title if isinstance(title, str) else None


async def preflight(client: httpx.AsyncClient, base_url: str) -> None:
    try:
        response = await client.get("/health")
    except httpx.HTTPError as exc:
        raise SystemExit(f"não alcancei {base_url}/health: {exc}") from exc
    if response.status_code == 200:
        return
    title = await _service_title(client)
    if title and "Settlr" not in title:
        raise SystemExit(
            f"{base_url} não é o gateway deste repositório. "
            f"Quem responde aí é «{title}», e essa API não tem /health. "
            "A porta 8000 está ocupada por outro serviço. "
            "Pare esse processo ou suba o gateway em outra porta e passe --base-url."
        )
    raise SystemExit(f"/health devolveu {response.status_code}: {response.text[:300]}")


async def login(client: httpx.AsyncClient, email: str, tenant: str) -> str:
    response = await client.post(
        "/auth/dev-login",
        json={"email": email, "tenant_slug": tenant, "role": "operador"},
    )
    if response.status_code == 404:
        raise SystemExit(
            "login de dev indisponível (ENV=prod ou tenant ausente). "
            "Fora de produção, rode: python -m app.cli seed-demo"
        )
    if response.status_code != 200:
        raise SystemExit(f"/auth/dev-login devolveu {response.status_code}: {response.text[:300]}")
    token = response.json().get("access_token")
    if not token:
        raise SystemExit("/auth/dev-login não devolveu access_token")
    return token


async def readiness(
    client: httpx.AsyncClient, routes: tuple[Route, ...], token: str
) -> None:
    print("prontidão")
    auth_failures = 0
    auth_routes = 0
    for route in routes:
        sample = await one_request(client, route, token)
        mark = "ok" if sample.error is None else sample.error
        status = sample.status or "-"
        print(f"  {route.label:<24} {status:>3}  {sample.latency_ms:6.0f} ms  {mark}")
        if route.auth:
            auth_routes += 1
            if sample.error:
                auth_failures += 1
    if auth_routes and auth_failures == auth_routes:
        raise SystemExit(
            "nenhuma rota do painel respondeu 2xx. "
            "Suba o gateway e os serviços de cobrança, conciliação e cadastro."
        )


def print_summary(summary: Summary, title: str) -> None:
    print(f"\n{title}")
    print(
        f"concorrência {summary.concurrency}  "
        f"duração {summary.duration_s:.1f}s  "
        f"requisições {summary.requests}  "
        f"erros {summary.errors} ({summary.error_rate:.2%})  "
        f"rps {summary.rps:.1f}"
    )
    print(
        f"latência ms  min {summary.min_ms:.0f}  p50 {summary.p50_ms:.0f}  "
        f"p95 {summary.p95_ms:.0f}  p99 {summary.p99_ms:.0f}  "
        f"máx {summary.max_ms:.0f}  média {summary.mean_ms:.0f}"
    )
    header = f"{'rota':<24} {'n':>7} {'rps':>8} {'p50':>8} {'p95':>8} {'p99':>8} {'erros':>7}"
    print(header)
    print("-" * len(header))
    for route in summary.routes:
        print(
            f"{route.route:<24} {route.requests:7d} {route.rps:8.1f} "
            f"{route.p50_ms:8.0f} {route.p95_ms:8.0f} {route.p99_ms:8.0f} {route.errors:7d}"
        )
    if summary.error_kinds:
        kinds = ", ".join(f"{name}={count}" for name, count in sorted(summary.error_kinds.items()))
        print(f"tipos de erro: {kinds}")


def summary_payload(summary: Summary) -> dict:
    payload = asdict(summary)
    payload["error_rate"] = summary.error_rate
    return payload


async def run_perf(client: httpx.AsyncClient, routes: tuple[Route, ...], token: str, args) -> dict:
    if args.warmup > 0:
        print(f"\naquecimento {args.warmup:g}s com concorrência {min(2, args.concurrency)}")
        await run_stage(client, routes, token, min(2, args.concurrency), args.warmup)

    print(f"\nperformance  concorrência {args.concurrency}  duração {args.duration:g}s")
    samples, elapsed = await run_stage(client, routes, token, args.concurrency, args.duration)
    summary = summarize(samples, args.concurrency, elapsed)
    print_summary(summary, "resultado")

    breaches: list[str] = []
    if summary.error_rate > args.max_error_rate:
        breaches.append(f"erros {summary.error_rate:.2%} > {args.max_error_rate:.2%}")
    if args.max_p95_ms is not None and summary.p95_ms > args.max_p95_ms:
        breaches.append(f"p95 {summary.p95_ms:.0f}ms > {args.max_p95_ms:.0f}ms")

    passed = not breaches
    if passed:
        print("\nlimite de performance respeitado")
    else:
        print("\nlimite de performance estourado: " + "; ".join(breaches))

    return {
        "passed": passed,
        "breaches": breaches,
        "stages": [summary_payload(summary)],
    }


async def run_stress(client: httpx.AsyncClient, routes: tuple[Route, ...], token: str, args) -> dict:
    print(
        f"\nstress  {args.start} → {args.max}  passo {args.step}  "
        f"{args.step_duration:g}s por degrau  "
        f"teto de erro {args.max_error_rate:.2%}  teto de p95 {args.max_p95_ms:.0f}ms"
    )
    stages: list[dict] = []
    healthy: int | None = None
    failed: int | None = None
    reason: str | None = None

    concurrency = args.start
    while concurrency <= args.max:
        print(f"\ndegrau  concorrência {concurrency}")
        samples, elapsed = await run_stage(client, routes, token, concurrency, args.step_duration)
        summary = summarize(samples, concurrency, elapsed)
        print_summary(summary, f"degrau {concurrency}")
        stages.append(summary_payload(summary))
        reason = saturation_reason(summary, args.max_error_rate, args.max_p95_ms)
        if reason:
            failed = concurrency
            print(f"saturado: {reason}")
            break
        healthy = concurrency
        concurrency += args.step

    if failed is None:
        print(f"\nnenhum degrau saturou até concorrência {args.max}")
    elif healthy is None:
        print("\no primeiro degrau já passou do limite")
    else:
        print(f"\núltimo degrau saudável: concorrência {healthy}")

    passed = failed is None or (healthy or 0) >= args.min_concurrency
    if args.min_concurrency and (healthy or 0) < args.min_concurrency:
        print(
            f"abaixo do mínimo: saudável {healthy or 0} < {args.min_concurrency}"
        )
        passed = False

    return {
        "passed": passed,
        "saturated": failed is not None,
        "reason": reason,
        "healthy_concurrency": healthy,
        "failed_concurrency": failed,
        "stages": stages,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Performance e stress test do gateway (somente leitura).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="gateway. O painel usa esta mesma porta.",
    )
    parser.add_argument("--email", default="operador@demo.local")
    parser.add_argument("--tenant", default="demo")
    parser.add_argument("--timeout", type=float, default=10.0, help="teto de cada request, em segundos")
    parser.add_argument("--allow-remote", action="store_true", help="permite alvo que não seja local")
    parser.add_argument("--json", dest="json_path", default=None, help="grava o relatório neste arquivo")
    parser.add_argument(
        "--routes",
        default=None,
        help="nomes separados por vírgula. Padrão: todas as leituras do painel.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    perf = sub.add_parser("perf", help="concorrência fixa", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    perf.add_argument("-c", "--concurrency", type=int, default=20)
    perf.add_argument("-d", "--duration", type=float, default=20, help="segundos de carga, fora o aquecimento")
    perf.add_argument("--warmup", type=float, default=3, help="segundos descartados antes da medição")
    perf.add_argument("--max-error-rate", type=float, default=0.01)
    perf.add_argument(
        "--max-p95-ms",
        type=float,
        default=None,
        help="se definido, o processo sai com erro quando o p95 passar deste valor",
    )

    stress = sub.add_parser(
        "stress",
        help="sobe a concorrência até saturar",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    stress.add_argument("--start", type=int, default=5)
    stress.add_argument("--step", type=int, default=5)
    stress.add_argument("--max", type=int, default=80)
    stress.add_argument("-d", "--step-duration", type=float, default=10, help="segundos por degrau")
    stress.add_argument("--max-error-rate", type=float, default=0.02)
    stress.add_argument("--max-p95-ms", type=float, default=2000)
    stress.add_argument(
        "--min-concurrency",
        type=int,
        default=0,
        help="sai com erro se o último degrau saudável ficar abaixo deste valor",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.timeout <= 0:
        raise SystemExit("--timeout precisa ser positivo")
    if args.mode == "perf":
        if args.concurrency < 1 or args.duration <= 0 or args.warmup < 0:
            raise SystemExit("perf: concorrência >= 1, duração > 0 e aquecimento >= 0")
        if args.max_error_rate < 0:
            raise SystemExit("--max-error-rate não pode ser negativo")
    if args.mode == "stress":
        if min(args.start, args.step, args.max) < 1 or args.start > args.max:
            raise SystemExit("stress: start, step e max >= 1, e start <= max")
        if args.step_duration <= 0 or args.max_error_rate < 0 or args.max_p95_ms <= 0:
            raise SystemExit("stress: duração e p95 positivos; taxa de erro >= 0")
        if args.min_concurrency < 0:
            raise SystemExit("--min-concurrency não pode ser negativo")


def pool_size(args: argparse.Namespace) -> int:
    if args.mode == "perf":
        return args.concurrency
    return args.max


async def amain(args: argparse.Namespace) -> int:
    if httpx is None:
        raise SystemExit(
            "httpx não encontrado. Rode com o venv da API: cd api && source .venv/bin/activate"
        )
    validate_args(args)
    base_url = args.base_url.rstrip("/")
    assert_safe_target(base_url, args.allow_remote)
    routes = select_routes(args.routes)
    names = ", ".join(route.name for route in routes)
    print(f"alvo {base_url}  modo {args.mode}  rotas {names}")

    limits = httpx.Limits(
        max_connections=pool_size(args),
        max_keepalive_connections=pool_size(args),
    )
    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        limits=limits,
        headers={"user-agent": "cobranca-loadtest"},
    ) as client:
        await preflight(client, base_url)
        token = await login(client, args.email, args.tenant)
        await readiness(client, routes, token)
        if args.mode == "perf":
            result = await run_perf(client, routes, token, args)
        else:
            result = await run_stress(client, routes, token, args)

    report = {
        "target": base_url,
        "mode": args.mode,
        "routes": [route.name for route in routes],
        "started_at": datetime.now(UTC).isoformat(),
        **result,
    }
    return (0 if result["passed"] else 1), report


def write_report(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"\nrelatório em {path}")


def main() -> None:
    args = build_parser().parse_args()
    report: dict | None = None
    try:
        code, report = asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("\ninterrompido")
        code = 130
    if args.json_path and report is not None:
        write_report(args.json_path, report)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
