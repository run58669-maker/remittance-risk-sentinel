"""Remittance Risk Sentinel — end-to-end orchestrator.

Each tick, over the Arbitrum stablecoin basket (MXNB / USDC / USDT):
  1. pull recent ERC-20 Transfer logs (resilient RPC: retry → breaker → fallback)
  2. detect large_transfer / fan_out / layering (degree-denoised)
  3. for the top critical/high anomalies, ask the LLM for a compliance note
  4. emit to console (and Telegram if TG_BOT_TOKEN is set)

Usage:
    python sentinel.py --demo      # replay the real 200-MXNB relay → guaranteed alert
    python sentinel.py --once      # one live pass over the basket
    python sentinel.py             # loop (default 60s)
"""
from __future__ import annotations

import argparse
import time

import flow_monitor as fm
import risk_note as rn
from resilient_llm import Scorecard

# how many blocks back to scan per tick, per token (Arbitrum ~4 blocks/s)
LIVE_WINDOW_BLOCKS = 1200
# only LLM-note the most serious anomalies (cost + signal control)
NOTE_SEVERITIES = {"critical", "high"}
MAX_NOTES_PER_TICK = 4
# real 200-MXNB relay block window (for --demo, a guaranteed live example)
DEMO_MXNB_WINDOW = (468157600, 468157850)

SEV_RANK = {"critical": 0, "high": 1, "flag": 2}


def emit(token_symbol: str, anomalies: list, llm_scorecard: Scorecard, tg=None) -> None:
    notable = sorted(
        [a for a in anomalies if a.severity in NOTE_SEVERITIES],
        key=lambda a: SEV_RANK.get(a.severity, 9),
    )
    counts = {}
    for a in anomalies:
        counts[a.kind] = counts.get(a.kind, 0) + 1
    summary = ", ".join(f"{k}:{v}" for k, v in counts.items()) or "clean"
    print(f"  [{token_symbol}] {summary}")

    for a in notable[:MAX_NOTES_PER_TICK]:
        note, meta = rn.write_note(a, scorecard=llm_scorecard)
        print(f"\n  ┌─ ALERT [{a.severity.upper()}] {token_symbol} · {a.kind}")
        for line in note.splitlines():
            print(f"  │ {line}")
        print(f"  └─ (LLM via {meta.get('via')})")
        if tg:
            tg.send_alert(wallet_tag=f"{token_symbol} {a.kind}", wallet_addr=a.addrs[0],
                          kind=a.kind, details=a.detail, interpretation=note)
    if len(notable) > MAX_NOTES_PER_TICK:
        print(f"  … +{len(notable) - MAX_NOTES_PER_TICK} more critical/high (capped this tick)")


def run_once(rpc, tokens, llm_scorecard, demo=False, tg=None, seen=None):
    for tok in tokens:
        if demo and tok["symbol"] == "MXNB":
            frm, to = DEMO_MXNB_WINDOW
        else:
            bn, _ = rpc.block_number()
            if bn is None:
                print(f"  [{tok['symbol']}] RPC chain exhausted"); continue
            frm, to = bn - LIVE_WINDOW_BLOCKS, bn
        _, anomalies, _ = fm.scan_window(rpc, tok, frm, to)
        if seen is not None:  # de-dup across ticks
            fresh = [a for a in anomalies if (sig := (a.kind, a.symbol, a.detail)) not in seen]
            for a in fresh:
                seen.add((a.kind, a.symbol, a.detail))
            anomalies = fresh
        emit(tok["symbol"], anomalies, llm_scorecard, tg=tg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--demo", action="store_true", help="replay the real 200-MXNB relay")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    tokens = fm.load_tokens()["tokens"]
    rpc = fm.arbitrum_rpc()
    llm_scorecard = Scorecard()
    tg = None  # Telegram wired when TG_BOT_TOKEN is configured

    seen: set = set()
    try:
        while True:
            print(f"\n=== Remittance Risk Sentinel · tick @ {time.strftime('%H:%M:%S')} "
                  f"{'(DEMO)' if args.demo else ''} ===")
            run_once(rpc, tokens, llm_scorecard, demo=args.demo, tg=tg,
                     seen=None if (args.once or args.demo) else seen)
            if args.once or args.demo:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + rpc.scorecard.render())
        if llm_scorecard.calls:
            print("LLM " + llm_scorecard.render())
        rpc.close()


if __name__ == "__main__":
    main()
