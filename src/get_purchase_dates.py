"""Query transaction dates for holdings - run on Pi to get actual purchase dates."""

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "portfolios.db")

def get_first_purchase_dates():
    """Get the first purchase date for each ticker in each portfolio."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get all active portfolios
    portfolios = {}
    for row in conn.execute('SELECT id, name FROM portfolios WHERE is_active = 1'):
        portfolios[row['id']] = {'name': row['name'], 'holdings': {}}

    # Get first BUY transaction for each ticker per portfolio
    query = """
        SELECT portfolio_id, ticker, MIN(executed_at) as first_purchase
        FROM transactions
        WHERE action = 'BUY'
        GROUP BY portfolio_id, ticker
        ORDER BY portfolio_id, ticker
    """

    for row in conn.execute(query):
        pid = row['portfolio_id']
        if pid in portfolios:
            portfolios[pid]['holdings'][row['ticker']] = row['first_purchase']

    conn.close()

    # Print results
    print("\n=== Purchase Dates by Portfolio ===\n")
    for pid, data in portfolios.items():
        print(f"{data['name']}:")
        for ticker, date in sorted(data['holdings'].items()):
            print(f"  {ticker}: {date}")
        print()

    return portfolios

if __name__ == '__main__':
    get_first_purchase_dates()
