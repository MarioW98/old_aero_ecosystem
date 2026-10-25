#!/usr/bin/env python3
"""
run_tests.py — Test runner unificato per l'ecosistema aero.

Esegue tutti i test autonomi del progetto (nessun framework esterno richiesto),
raccoglie gli esiti e stampa un riepilogo finale con i tempi di esecuzione.

Uso:
    python run_tests.py                    # esegue tutta la suite automatizzata
    python run_tests.py --list             # elenca i test senza eseguirli
    python run_tests.py --filter synthesis # esegue solo i test il cui nome contiene "synthesis"
    python run_tests.py --include-manual   # include anche i tool demo interattivi (GUI)
    python run_tests.py --verbose          # stampa l'output completo di ogni test
    python run_tests.py --skip-long        # salta il test end-to-end di ~60s

Uscita:
    0 = tutti i test PASS, 1 = almeno un test FALLITO o timeout.

Note:
    - Su Linux i test Qt vengono eseguiti con QT_QPA_PLATFORM=offscreen (headless).
    - I tool "manuali" aprono finestre o girano all'infinito: non fanno parte del CI.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMEOUT_S = 240  # timeout per singolo test

# --------------------------------------------------------------------------
# Classificazione dei test
# --------------------------------------------------------------------------

# Tool demo/interattivi: aprono finestre o pubblicano telemetria in loop.
# Non sono test di asserzione: si lanciano a mano per ispezione visiva.
MANUAL_TESTS = {
    "tools/test_dialog_standalone.py",    # apre un dialog Qt a schermo
    "tools/test_publisher.py",            # pubblica telemetria finti-dati in loop
    "tools/test_sim_launch_dialog.py",    # apre il dialog di lancio simulazione
}

# Test lunghi (end-to-end): inclusi di default, skipponabili con --skip-long
LONG_TESTS = {
    "test_zmq_integration.py",            # smoke test end-to-end, ~30s con durata limitata
}

# Timeout dedicati per test particolarmente lunghi
TEST_TIMEOUTS = {
    "test_zmq_integration.py": 90,
}

# Argomenti extra da passare a test specifici:
# test_zmq_integration gira all'infinito con duration=0 (default): nel suite
# viene limitato a 30s come smoke test end-to-end.
TEST_ARGS = {
    "test_zmq_integration.py": ["--duration", "30"],
}


def discover_tests() -> list[Path]:
    """Scopre tutti i test_*.py del progetto (root, simulator/, tools/)."""
    tests: list[Path] = []
    for folder in (ROOT, ROOT / "simulator", ROOT / "tools"):
        if folder.is_dir():
            tests.extend(sorted(folder.glob("test_*.py")))
    return sorted(set(tests), key=lambda p: (p.parent.name, p.name))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def run_one(test: Path, verbose: bool) -> tuple[bool, float, str]:
    """Esegue un singolo test. Ritorna (passato, durata_s, coda_output)."""
    env = os.environ.copy()
    # Su Linux (CI headless) Qt deve usare la piattaforma offscreen.
    # Su Windows/macOS si lascia la piattaforma nativa.
    if sys.platform.startswith("linux"):
        env.setdefault("QT_QPA_PLATFORM", "offscreen")

    timeout = TEST_TIMEOUTS.get(test.name, TIMEOUT_S)
    cmd = [sys.executable, str(test), *TEST_ARGS.get(test.name, [])]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        ok = proc.returncode == 0
        tail = (proc.stdout + proc.stderr).strip().splitlines()
        detail = "\n".join(tail if verbose else tail[-8:])
        return ok, elapsed, detail
    except subprocess.TimeoutExpired:
        return False, time.monotonic() - t0, f"TIMEOUT dopo {timeout}s"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test runner dell'ecosistema aero")
    parser.add_argument("--list", action="store_true", help="elenca i test ed esce")
    parser.add_argument("--filter", metavar="NOME", help="esegue solo i test che contengono NOME")
    parser.add_argument("--include-manual", action="store_true",
                        help="include i tool demo interattivi (GUI)")
    parser.add_argument("--skip-long", action="store_true",
                        help="salta i test end-to-end lunghi (~60s)")
    parser.add_argument("--verbose", action="store_true", help="output completo dei test")
    args = parser.parse_args()

    all_tests = discover_tests()

    manual = {t for t in all_tests if rel(t) in MANUAL_TESTS}
    long_t = {t for t in all_tests if t.name in LONG_TESTS}
    suite = [t for t in all_tests if t not in manual and t not in long_t]
    if not args.skip_long:
        suite += [t for t in long_t]
    if args.include_manual:
        suite += [t for t in manual]
    suite.sort(key=lambda p: (p.parent.name, p.name))

    if args.filter:
        suite = [t for t in suite if args.filter.lower() in t.stem.lower()]

    if args.list:
        print(f"Suite selezionata ({len(suite)} test):")
        for t in suite:
            tag = " [LONG]" if t in long_t else (" [MANUALE]" if t in manual else "")
            print(f"  {rel(t)}{tag}")
        skipped = [t for t in all_tests if t not in suite]
        if skipped:
            print("\nEsclusi da questa esecuzione:")
            for t in skipped:
                print(f"  {rel(t)}")
        return 0

    if not suite:
        print("Nessun test selezionato.")
        return 1

    print(f"Suite: {len(suite)} test | Python {sys.version.split()[0]} | "
          f"piattaforma {sys.platform}\n" + "=" * 70)

    results: list[tuple[str, bool, float, str]] = []
    for i, test in enumerate(suite, 1):
        name = rel(test)
        print(f"\n[{i}/{len(suite)}] {name}", flush=True)
        ok, elapsed, detail = run_one(test, args.verbose)
        status = "PASS" if ok else "FAIL"
        print(f"  -> {status} ({elapsed:.1f}s)")
        if detail and (not ok or args.verbose):
            print("  " + detail.replace("\n", "\n  "))
        results.append((name, ok, elapsed, detail))

    # --------------------------- Riepilogo ---------------------------
    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    total_time = sum(r[2] for r in results)

    print("\n" + "=" * 70)
    print(f"RIEPILOGO: {len(passed)} PASS / {len(failed)} FAIL  "
          f"(tempo totale {total_time:.1f}s)")
    if failed:
        print("\nTest falliti:")
        for name, _, elapsed, detail in failed:
            print(f"  ✗ {name} ({elapsed:.1f}s)")
            for line in detail.splitlines()[-3:]:
                print(f"      {line}")
        return 1
    print("Tutti i test sono passati. ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Output troncato a valle (es. pipe verso `head`): esce senza traceback.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
