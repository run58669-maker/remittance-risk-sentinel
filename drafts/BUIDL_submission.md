# BUIDL submission — MXNB Treasury Sentinel

*(paste into the DoraHacks BUIDL form. Fill the two links marked ⟨ ⟩ after you
upload the video and push the repo.)*

---

**Name:** MXNB Treasury Sentinel

**Tagline:** An AI risk co-pilot for the *issuer* of MXNB — live, resilient, on-chain monitoring of Bitso/Juno's Mexican-peso stablecoin on Arbitrum.

**Track / theme:** AI × Blockchain · stablecoins / payments (Bitso)

**Demo video:** ⟨YOUTUBE_LINK — upload build/demo/demo.mp4⟩
**Repo:** https://github.com/run58669-maker/remittance-risk-sentinel

---

## The problem

A regulated stablecoin issuer already does KYC at the on/off-ramp. What it does **not** get off the shelf is a live, on-chain view of its **own** token's health: how much is being minted vs redeemed, sudden supply swings, holder concentration, large settlement flows — the things that move reserve coverage and peg risk. That's a treasury & risk desk function, and today nobody is watching MXNB on-chain *for the issuer*.

This is deliberately **not** third-party AML surveillance of strangers' wallets (a regulated issuer can't and doesn't police pseudonymous EOAs). It's the issuer watching its own coin.

## What it does

Each tick, over Arbitrum, the Sentinel:

- Pulls MXNB's ERC-20 Transfer logs and flags **issuer signals** — `mint` / `redemption` (via the zero address), `net supply swing`, `large circulation`, `holder concentration`.
- Watches the surrounding **USD corridor** (USDC / USDT) for context.
- Turns each notable event into a **treasury-desk note** via an LLM — `SIGNAL / WHY / CONFIDENCE / ACTION`, framed in reserve-coverage / redemption-pressure / peg-stress terms. The model only restates the real on-chain figures; the detection is real math, the LLM just explains it.
- Pushes alerts to **Telegram** for the desk.

## Why it's solid (not a thin wrapper)

- **Real on-chain data** — live Arbitrum logs for the real MXNB contract (`0xf197…80aa`); the `--demo` replays a real 200-MXNB mint.
- **Resilience, demonstrated** — both the RPC and the LLM run behind a retry → circuit-breaker → fallback chain. `python chaos.py` kills the primary provider mid-call and the request still succeeds; the scorecard shows fallback rate 100%, MTTR ~1s. Shown, not claimed.
- **Honest about scope** — MXNB on-chain volume is still sparse (most flow is off-chain via Juno rails); the tool logs *every* issuance/redemption and uses the USD corridor for live-volume context. We don't overclaim.

## How to run (judges: one command)

```
pip install -r requirements.txt
python sentinel.py --demo   # real MXNB mint → treasury note
python chaos.py             # kill the primary LLM → watch the fallback recover
```

## Stack

Python · Arbitrum (public RPC) · OpenAI-compatible LLM gateway (TrueFoundry / Groq) · Telegram Bot API · MIT.

## Roadmap

Telegram alert feed (done) · holder-concentration via balance snapshots · depeg / peg-deviation feed · account-abstraction session-key alert subscriptions · contract-label denoising for the corridor signals.
