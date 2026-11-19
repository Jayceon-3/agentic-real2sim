"""Summarize Codex CLI session logs (~/.codex/sessions/.../rollout-*.jsonl) for an experiment record,
including an API-equivalent cost estimate.

Usage: python3 scripts/codex_session_stats.py ROLLOUT.jsonl [ROLLOUT2.jsonl ...] [--json]

Several files (the main session plus reviewer sessions) are summed into one total.
The cost is what the same tokens would cost on the OpenAI API at standard-tier
list prices. Runs on a ChatGPT subscription are not billed per token.
AHa-3D's reviewer runs `codex exec --ephemeral`, which saves no session; launch Codex
with experiments/bin on PATH to keep those sessions (see experiments/README.md).
"""
import json, sys
from collections import Counter
from datetime import datetime

# USD per 1M tokens, OpenAI standard tier, prompts <= 272K input tokens.
# Source: https://developers.openai.com/api/docs/pricing (checked 2026-10-22).
# Reasoning tokens are part of output_tokens in Codex logs and bill as output.
PRICES = {
    'gpt-6-astra': {'input': 10.00, 'cached_input': 1.00, 'cache_write': 12.50, 'output': 50.00},
}
LONG_CONTEXT_INPUT = 272_000  # above this, OpenAI charges long-context rates for the request


def summarize(path):
    kinds, tok, meta, ctx = Counter(), None, {}, {}
    first = last = None
    long_requests = 0
    for line in open(path):
        e = json.loads(line)
        p = e.get('payload') or {}
        sub = p.get('type') if isinstance(p, dict) else None
        kinds[(e.get('type'), sub)] += 1
        ts = e.get('timestamp')
        if ts:
            first = first or ts
            last = ts
        if e.get('type') == 'session_meta':
            meta = {k: p.get(k) for k in ('id', 'cwd', 'cli_version', 'originator', 'source')}
        if e.get('type') == 'turn_context':
            ctx = {k: p.get(k) for k in ('model', 'effort', 'approval_policy', 'sandbox_policy')}
        if sub == 'token_count' and p.get('info'):
            tok = p['info']['total_token_usage']
            if (p['info'].get('last_token_usage') or {}).get('input_tokens', 0) > LONG_CONTEXT_INPUT:
                long_requests += 1
    parse = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
    return {
        'file': path, **meta, **ctx,
        'start_utc': first, 'end_utc': last,
        'wall_minutes': round((parse(last) - parse(first)).total_seconds() / 60, 1) if first else None,
        'tool_calls': kinds[('response_item', 'custom_tool_call')] + kinds[('response_item', 'function_call')],
        'assistant_messages': kinds[('response_item', 'message')],
        'context_compactions': kinds[('compacted', None)],
        'long_context_requests': long_requests,
        'tokens': tok or {},
    }


def cost(tokens, model):
    price = PRICES.get(model)
    if not price or not tokens:
        return None
    cached = tokens.get('cached_input_tokens', 0)
    write = tokens.get('cache_write_input_tokens', 0)
    uncached = tokens.get('input_tokens', 0) - cached - write
    parts = {
        'uncached_input': uncached * price['input'] / 1e6,
        'cached_input': cached * price['cached_input'] / 1e6,
        'cache_write': write * price['cache_write'] / 1e6,
        'output': tokens.get('output_tokens', 0) * price['output'] / 1e6,
    }
    return {**{k: round(v, 2) for k, v in parts.items()}, 'total_usd': round(sum(parts.values()), 2)}


def main(argv):
    files = [a for a in argv if not a.startswith('--')]
    sessions = [summarize(f) for f in files]
    total = Counter()
    for s in sessions:
        s['cost_usd'] = cost(s['tokens'], s.get('model'))
        total.update({k: v for k, v in s['tokens'].items() if isinstance(v, int)})
    usd = sum((s['cost_usd'] or {}).get('total_usd', 0) for s in sessions)
    out = {'sessions': sessions, 'total_tokens': dict(total), 'total_cost_usd': round(usd, 2),
           'unpriced_models': sorted({s.get('model') for s in sessions if s['cost_usd'] is None}),
           'long_context_warning': any(s['long_context_requests'] for s in sessions)}
    if '--json' in argv:
        print(json.dumps(out, indent=1, default=str))
        return
    for s in sessions:
        print(f"== {s['file']}")
        for k, v in s.items():
            if k != 'file':
                print(f'  {k}: {v}')
    print(f"TOTAL tokens: {dict(total)}")
    print(f"TOTAL API-equivalent cost: ${usd:.2f} (standard-tier list prices; not actual subscription spend)")
    if out['unpriced_models']:
        print(f"WARNING: no price for {out['unpriced_models']}; add them to PRICES")
    if out['long_context_warning']:
        print("WARNING: some requests exceeded 272K input tokens; long-context rates apply and are not modeled")


if __name__ == '__main__':
    main(sys.argv[1:])
