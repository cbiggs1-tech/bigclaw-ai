"""Generate portfolio performance comparison chart."""

import os
import sqlite3
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import yfinance as yf
import pandas as pd

# Paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, 'src', 'portfolios.db')
CHART_PATH = os.path.join(REPO_ROOT, 'docs', 'data', 'performance_chart.png')


def get_portfolio_transactions():
    """Get all transactions grouped by portfolio."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    portfolios = {}
    for row in conn.execute('SELECT id, name, starting_cash FROM portfolios WHERE is_active = 1'):
        portfolios[row['id']] = {
            'name': row['name'],
            'starting_cash': row['starting_cash'],
            'transactions': []
        }

    for row in conn.execute('SELECT * FROM transactions ORDER BY executed_at'):
        pid = row['portfolio_id']
        if pid in portfolios:
            portfolios[pid]['transactions'].append({
                'ticker': row['ticker'],
                'action': row['action'],
                'shares': row['shares'],
                'price': row['price'],
                'executed_at': row['executed_at']
            })

    conn.close()
    return portfolios


def get_historical_prices(tickers, start_date, end_date):
    """Fetch historical prices for all tickers."""
    if not tickers:
        return pd.DataFrame()

    try:
        data = yf.download(list(tickers), start=start_date, end=end_date, progress=False)
        if len(tickers) == 1:
            if 'Close' in data.columns:
                return data['Close'].to_frame(name=list(tickers)[0])
        else:
            if 'Close' in data.columns:
                return data['Close']
    except Exception as e:
        print(f"Error fetching prices: {e}")
    return pd.DataFrame()


def calculate_daily_values(portfolios, start_date, end_date):
    """Calculate daily portfolio values."""
    # Collect all tickers
    all_tickers = set()
    for p in portfolios.values():
        for t in p['transactions']:
            all_tickers.add(t['ticker'])

    print(f"Fetching prices for: {all_tickers}")

    # Get historical prices
    prices = get_historical_prices(all_tickers, start_date, end_date)
    if prices.empty:
        print("No price data retrieved")
        return {}

    print(f"Got prices for dates: {prices.index.tolist()}")

    results = {}
    for pid, portfolio in portfolios.items():
        daily_values = []
        holdings = {}  # ticker -> shares
        cash = portfolio['starting_cash']

        # Sort transactions by date
        sorted_txns = sorted(portfolio['transactions'], key=lambda x: x['executed_at'])
        txn_idx = 0

        for date in prices.index:
            date_str = date.strftime('%Y-%m-%d')

            # Process transactions up to and including this date
            while txn_idx < len(sorted_txns):
                t = sorted_txns[txn_idx]
                t_date = t['executed_at'][:10]
                if t_date <= date_str:
                    ticker = t['ticker']
                    shares = t['shares']
                    price = t['price']

                    if t['action'] == 'BUY':
                        holdings[ticker] = holdings.get(ticker, 0) + shares
                        cash -= shares * price
                    elif t['action'] == 'SELL':
                        holdings[ticker] = holdings.get(ticker, 0) - shares
                        cash += shares * price
                    txn_idx += 1
                else:
                    break

            # Calculate portfolio value
            holdings_value = 0
            for ticker, shares in holdings.items():
                if ticker in prices.columns:
                    price = prices.loc[date, ticker]
                    if not pd.isna(price):
                        holdings_value += shares * price

            total_value = cash + holdings_value
            if total_value > 0:
                return_pct = ((total_value - portfolio['starting_cash']) / portfolio['starting_cash']) * 100
                daily_values.append({
                    'date': date,
                    'value': total_value,
                    'return_pct': return_pct
                })

        results[portfolio['name']] = daily_values
        print(f"{portfolio['name']}: {len(daily_values)} data points")

    return results


def generate_chart(daily_values):
    """Generate the comparison chart."""
    if not daily_values:
        print("No data to chart")
        return False

    # Set up the figure with dark theme
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    # Color palette
    colors = {
        'Value Picks': '#4ade80',      # Green
        'Innovation Fund': '#f87171',  # Red/coral
        'Growth Value': '#60a5fa'      # Blue
    }

    # Plot each portfolio
    for name, values in daily_values.items():
        if values:
            dates = [v['date'] for v in values]
            returns = [v['return_pct'] for v in values]
            color = colors.get(name, '#ffffff')
            ax.plot(dates, returns, label=f"{name} ({returns[-1]:+.2f}%)", linewidth=2.5, color=color, marker='o', markersize=5)

    # Styling
    ax.set_xlabel('Date', fontsize=11, color='#e5e5e5')
    ax.set_ylabel('Return (%)', fontsize=11, color='#e5e5e5')
    ax.set_title('Portfolio Performance Comparison (Since Feb 3, 2026)', fontsize=14, fontweight='bold', color='white', pad=15)

    # Add zero line
    ax.axhline(y=0, color='#4a4a6a', linestyle='--', linewidth=1, alpha=0.7)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    plt.xticks(rotation=45, ha='right')

    # Grid
    ax.grid(True, alpha=0.2, color='#4a4a6a')

    # Legend
    ax.legend(loc='upper left', framealpha=0.9, facecolor='#1a1a2e', edgecolor='#4a4a6a')

    # Spine colors
    for spine in ax.spines.values():
        spine.set_color('#4a4a6a')
    ax.tick_params(colors='#e5e5e5')

    # Save
    plt.tight_layout()
    os.makedirs(os.path.dirname(CHART_PATH), exist_ok=True)
    plt.savefig(CHART_PATH, dpi=150, facecolor='#1a1a2e', edgecolor='none')
    plt.close()

    print(f"Chart saved to {CHART_PATH}")
    return True


def main():
    # Date range: Feb 3, 2026 to today
    start_date = '2026-02-03'
    end_date = datetime.now().strftime('%Y-%m-%d')

    print(f"Generating chart for {start_date} to {end_date}")

    # Get portfolio data
    portfolios = get_portfolio_transactions()
    print(f"Found {len(portfolios)} portfolios")

    for pid, p in portfolios.items():
        print(f"  {p['name']}: {len(p['transactions'])} transactions")

    # Calculate daily values
    daily_values = calculate_daily_values(portfolios, start_date, end_date)

    # Generate chart
    success = generate_chart(daily_values)
    return success


if __name__ == '__main__':
    main()
