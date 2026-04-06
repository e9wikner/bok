#!/usr/bin/env python3
"""
Fix SIE4 encoding corruption in voucher descriptions.

During SIE4 import, CP437-encoded bytes were decoded as Latin-1 (ISO-8859-1),
causing Swedish characters to be stored as raw C1 control codepoints
(e.g. U+0094 instead of ö, U+0084 instead of ä).

This script finds all affected vouchers and corrects their descriptions
via the API, which records the change in the audit trail.
"""

import json
import sys
import urllib.request

API_BASE = "http://localhost:8000"
API_KEY = "dev-key-change-in-production"
REASON = "Fix SIE4 encoding corruption (CP437 chars stored as Latin-1 raw bytes)"


def api_request(method, path, data=None):
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def is_corrupted(text):
    """Check if text contains C1 control characters (U+0080-U+009F)."""
    return any(0x80 <= ord(c) <= 0x9F for c in text)


def fix_description(text):
    """Reverse the Latin-1 mis-decode and re-decode as CP437."""
    return text.encode("latin-1").decode("cp437")


def main():
    # Fetch all vouchers
    vouchers = api_request("GET", "/api/v1/vouchers?status=all&limit=1000")
    all_vouchers = vouchers.get("vouchers", [])
    print(f"Total vouchers: {len(all_vouchers)}")

    fixed = 0
    errors = 0

    for v in all_vouchers:
        desc = v.get("description", "")
        if not is_corrupted(desc):
            continue

        new_desc = fix_description(desc)
        voucher_id = v["id"]

        # Get full voucher to preserve rows
        full = api_request("GET", f"/api/v1/vouchers/{voucher_id}")
        rows = [
            {
                "account": r["account_code"],
                "debit": r["debit"],
                "credit": r["credit"],
                "description": r.get("description"),
            }
            for r in full["rows"]
        ]

        try:
            api_request(
                "PUT",
                f"/api/v1/vouchers/{voucher_id}",
                {
                    "description": new_desc,
                    "rows": rows,
                    "reason": REASON,
                    "teach_ai": False,
                },
            )
            print(f"  Fixed {voucher_id}: {repr(desc)} -> {new_desc}")
            fixed += 1
        except Exception as e:
            print(f"  ERROR {voucher_id}: {e}", file=sys.stderr)
            errors += 1

    print(f"\nDone. Fixed: {fixed}, Errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
