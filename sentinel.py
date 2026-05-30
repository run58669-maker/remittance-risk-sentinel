"""MXNB Treasury Sentinel — end-to-end orchestrator.

Issuer co-pilot for MXNB (Juno/Bitso peso stablecoin on Arbitrum): each tick it
watches MXNB's own on-chain health (mint / redeem / net supply / concentration)
and, for context, the broader USD-stablecoin corridor (USDC/USDT circulation).
Anomalies get an LLM-written treasury-risk note; resilience scorecards prove the
RPC + LLM fallback chains.

Usage:
    python sentinel.py --demo   # replay a real MXNB issuance+relay window
    python sentinel.py --once   # one live pass
    python sentinel.py          # loop (default 60s)
"""
from __future__ import annotations

import argparse
import sys
import time

try:  # keep the demo from dying on non-ASCII output on legacy consoles (e.g. Windows GBK)
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import flow_monitor as fm
import risk_note as rn
import treasury as tr
from tg_bot import TGBot

LIVE_WINDOW_BLOCKS = 1200
NOTE_SEVERITIES = {"critical", "high"}
MAX_NOTES_PER_TICK = 4
DEMO_MXNB_WINDOW = (468157600, 468157850)  # a real MXNB mint + 200-relay window
SEV_RANK = {"critical": 0, "high": 1, "flag": 2}


def emit(symbol: str, anomalies: list, tg=None, do_notes: bool = True) -> None:
    notable = sorted([a for a in anomalies if a.severity in NOTE_SEVERITIES],
                     key=lambda a: SEV_RANK.get(a.severity, 9))
    counts: dict[str, int] = {}
    for a in anomalies:
        counts[a.kind] = counts.get(a.kind, 0) + 1
    suffix = "" if do_notes else "  (corridor context — counts only)"
    print(f"  [{symbol}] " + (", ".join(f"{k}:{v}" for k, v in counts.items()) or "clean") + suffix)
    if not do_notes:
        return
    for a in notable[:MAX_NOTES_PER_TICK]:
        note, meta = rn.write_note(a)
        print(f"\n  ┌─ ALERT [{a.severity.upper()}] {symbol} · {a.kind}")
        for line in note.splitlines():
            print(f"  │ {line}")
        print(f"  └─ (LLM via {meta.get('via')})")
        if tg:
            ok, info = tg.send_alert(wallet_tag=f"{symbol} {a.kind}",
                                     wallet_addr=(a.addrs[0] if a.addrs else "-"),
                                     kind=a.kind, details=a.detail, interpretation=note)
            print(f"  └─ TG: {'sent OK, msg ' + str(info) if ok else 'FAILED ' + str(info)}")
    if len(notable) > MAX_NOTES_PER_TICK:
        print(f"  … +{len(notable) - MAX_NOTES_PER_TICK} more critical/high (capped)")


def run_once(rpc, tokens, demo=False, tg=None, seen=None) -> None:
    for tok in tokens:
        is_mxnb = tok["symbol"] == "MXNB"
        if demo and is_mxnb:
            frm, to = DEMO_MXNB_WINDOW
        else:
            bn, _ = rpc.block_number()
            if bn is None:
                print(f"  [{tok['symbol']}] RPC chain exhausted"); continue
            frm, to = bn - LIVE_WINDOW_BLOCKS, bn

        if is_mxnb:
            summary, anomalies = tr.scan_treasury(rpc, tok, frm, to)
            print(f"  [MXNB treasury] minted {summary['minted']:,.2f} / "
                  f"redeemed {summary['redeemed']:,.2f} / net Δ {summary['net_supply_delta']:+,.2f} "
                  f"({summary['transfers']} transfers)")
        else:
            _, anomalies, _ = fm.scan_window(rpc, tok, frm, to)

        if seen is not None:
            anomalies = [a for a in anomalies
                         if (a.kind, a.symbol, a.detail) not in seen
                         and not seen.add((a.kind, a.symbol, a.detail))]
        emit(tok["symbol"], anomalies, tg=tg, do_notes=is_mxnb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    tokens = fm.load_tokens()["tokens"]
    rpc = fm.arbitrum_rpc()
    _tg = TGBot()                       # reads TG_BOT_TOKEN / TG_CHAT_ID from .env
    tg = _tg if _tg.token else None
    print("  (Telegram alerts: " + ("ON" if tg else "off — no TG_BOT_TOKEN") + ")")
    seen: set = set()
    try:
        while True:
            print(f"\n=== MXNB Treasury Sentinel · tick @ {time.strftime('%H:%M:%S')} "
                  f"{'(DEMO)' if args.demo else ''} ===")
            run_once(rpc, tokens, demo=args.demo, tg=tg,
                     seen=None if (args.once or args.demo) else seen)
            if args.once or args.demo:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + rpc.scorecard.render())
        if rn.scorecard().calls:
            print("LLM " + rn.scorecard().render())
        rpc.close()


if __name__ == "__main__":
    main()
