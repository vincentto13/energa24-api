#!/usr/bin/env python3
"""Quick smoke test for the energa library."""
import asyncio
import os
import pathlib
import sys

USERNAME = os.environ["ENERGA_USERNAME"]
PASSWORD = os.environ["ENERGA_PASSWORD"]


async def test_async():
    from energa import EnergaClient, EnergaForbiddenError

    print("=== Async client ===")
    async with EnergaClient(USERNAME, PASSWORD) as client:
        print(f"Clients: {len(client.clients)}")
        for c in client.clients:
            print(f"  {c.name} ({c.client_number}) — {len(c.accounts)} account(s)")

        for account in client.accounts:
            acc = account.account_number

            balance = await client.get_balance(acc)
            print(f"\n  [{acc}] balance: {balance.balance} PLN ({balance.status})")

            invoices = await client.get_invoices(acc)
            print(f"  [{acc}] invoices: {len(invoices)}")
            for inv in invoices[:2]:
                print(f"    {inv.invoice_number}  {inv.issue_date}  {inv.amount} PLN  {inv.status}  downloadable={inv.downloadable}")

            # Download first downloadable invoice
            first_dl = next((i for i in invoices if i.downloadable), None)
            if first_dl:
                try:
                    pdf = await client.download_invoice(acc, first_dl.dms_id)
                    fname = f"{first_dl.invoice_number.replace('/', '_')}.pdf"
                    pathlib.Path(fname).write_bytes(pdf)
                    print(f"  [{acc}] saved {fname} ({len(pdf):,} bytes)")
                except EnergaForbiddenError:
                    print(f"  [{acc}] download not permitted by server")


def test_sync():
    from energa import EnergaClientSync, EnergaForbiddenError

    print("\n=== Sync client ===")
    with EnergaClientSync(USERNAME, PASSWORD) as client:
        for account in client.accounts:
            acc = account.account_number
            balance = client.get_balance(acc)
            print(f"  [{acc}] balance: {balance.balance} PLN")


if __name__ == "__main__":
    asyncio.run(test_async())
    test_sync()
