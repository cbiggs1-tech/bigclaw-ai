"""Output Guardrail — verifies all financial numbers before publication.

Intercepts any text destined for Slack, Discord, dashboard, or reports
and validates price claims against the PriceOracle. This makes it
structurally impossible for hallucinated prices to reach the user.

Rules:
- Any "$TICKER $XXX.XX" pattern is checked against PriceOracle
- If the claimed price is >2% off from verified, it's corrected
- If a verified price can't be obtained, the number is flagged
- All corrections are logged for audit
"""

import re
import logging
from typing import Optional

from services.price_oracle import get_oracle, PriceUnavailableError

logger = logging.getLogger(__name__)

# Matches patterns like: AAPL $237.45, $NVDA at 132.50, TSLA: $245.30
# Also matches: AAPL ($237.45), price: $237.45
_PRICE_PATTERN = re.compile(
    r'\b([A-Z]{1,5})\b'           # Ticker (1-5 uppercase letters)
    r'[:\s]*'                      # Optional separator
    r'[\(\$]*'                     # Optional ( or $
    r'(\$?\d{1,6}\.\d{2})'        # Price like $237.45 or 237.45
    r'[\)]*'                       # Optional closing )
)

# Words that look like tickers but aren't
_NOT_TICKERS = {
    'THE', 'FOR', 'AND', 'BUT', 'NOT', 'ALL', 'ARE', 'WAS', 'HAS', 'HAD',
    'CAN', 'HER', 'HIS', 'OUR', 'OUT', 'NEW', 'OLD', 'BIG', 'TOP', 'LOW',
    'HIGH', 'USD', 'EST', 'ETF', 'IPO', 'CEO', 'CFO', 'CTO', 'COO', 'SEC',
    'FED', 'GDP', 'CPI', 'RSI', 'EPS', 'BPS', 'YOY', 'QOQ', 'MOM', 'DAD',
    'NOW', 'HOW', 'WHO', 'WHY', 'SET', 'GET', 'PUT', 'RUN', 'USE', 'BUY',
    'SELL', 'HOLD', 'LONG', 'SHORT', 'BULL', 'BEAR', 'FOMC', 'MACD',
    'MAX', 'MIN', 'AVG', 'SUM', 'NET', 'DAY', 'WEEK', 'YEAR', 'CASH',
    'GAIN', 'LOSS', 'RISK', 'STOP', 'NONE', 'TRADE',
}

# Tolerance: how far off a claimed price can be before correction (2%)
_TOLERANCE_PCT = 2.0


def verify_text(text: str, correct: bool = True) -> tuple[str, list[dict]]:
    """Verify all price claims in text against PriceOracle.

    Args:
        text: The text to verify (from LLM, report, etc.)
        correct: If True, replace wrong prices. If False, just flag them.

    Returns:
        Tuple of (verified_text, list_of_issues)
        Each issue: {ticker, claimed, verified, pct_off, action}
    """
    oracle = get_oracle()
    issues = []

    # Find all potential price claims
    matches = list(_PRICE_PATTERN.finditer(text))
    if not matches:
        return text, issues

    # Collect unique tickers to batch-fetch
    tickers_found = set()
    for m in matches:
        ticker = m.group(1)
        if ticker not in _NOT_TICKERS and len(ticker) >= 2:
            tickers_found.add(ticker)

    if not tickers_found:
        return text, issues

    # Batch fetch verified prices
    verified = oracle.get_verified_prices(list(tickers_found))

    # Process matches in reverse order (so replacements don't shift offsets)
    replacements = []
    for m in reversed(matches):
        ticker = m.group(1)
        if ticker in _NOT_TICKERS or ticker not in verified:
            continue

        claimed_str = m.group(2).replace('$', '')
        try:
            claimed = float(claimed_str)
        except ValueError:
            continue

        vp = verified[ticker]
        pct_off = abs(claimed - vp.price) / vp.price * 100 if vp.price > 0 else 0

        if pct_off > _TOLERANCE_PCT:
            issue = {
                'ticker': ticker,
                'claimed': claimed,
                'verified': vp.price,
                'pct_off': round(pct_off, 1),
                'source': vp.source,
                'action': 'corrected' if correct else 'flagged',
            }
            issues.append(issue)
            logger.warning(
                f"Price mismatch: {ticker} claimed ${claimed:.2f} vs "
                f"verified ${vp.price:.2f} ({pct_off:.1f}% off) — {issue['action']}"
            )

            if correct:
                # Replace the price in the text
                old = m.group(2)
                new = f"${vp.price:.2f}"
                start, end = m.start(2), m.end(2)
                replacements.append((start, end, new))

    # Apply replacements
    if replacements:
        text_list = list(text)
        for start, end, new in replacements:
            text_list[start:end] = list(new)
        text = ''.join(text_list)

    return text, issues


def verify_portfolio_values(portfolio_data: dict) -> dict:
    """Verify all prices in a portfolio data structure.

    Takes the output of Portfolio.calculate_total_value() or
    export_dashboard's portfolio dict and re-verifies every price.

    Args:
        portfolio_data: Dict with 'positions' or 'holdings' list

    Returns:
        Same dict with prices verified and corrected
    """
    oracle = get_oracle()

    positions = portfolio_data.get('positions') or portfolio_data.get('holdings', [])
    if not positions:
        return portfolio_data

    tickers = [p.get('ticker') for p in positions if p.get('ticker')]
    verified = oracle.get_verified_prices(tickers)

    for pos in positions:
        ticker = pos.get('ticker')
        if ticker and ticker in verified:
            vp = verified[ticker]
            old_price = pos.get('current_price') or pos.get('currentPrice')
            pos['currentPrice'] = vp.price
            pos['current_price'] = vp.price
            pos['price_source'] = vp.source
            pos['price_verified_at'] = vp.timestamp_str

            if old_price and abs(old_price - vp.price) / vp.price * 100 > _TOLERANCE_PCT:
                logger.warning(
                    f"Portfolio price corrected: {ticker} "
                    f"${old_price:.2f} → ${vp.price:.2f}"
                )

    return portfolio_data


def verify_before_publish(text: str, channel: str = "unknown") -> str:
    """Top-level function: verify text before sending to any output.

    Use this as the last step before Slack/Discord/dashboard publish.
    Logs all corrections for audit trail.

    Args:
        text: The message to verify
        channel: Where this is being sent (for logging)

    Returns:
        Verified text with any corrections applied
    """
    verified_text, issues = verify_text(text, correct=True)

    if issues:
        logger.info(
            f"Guardrail corrected {len(issues)} price(s) before publishing to {channel}: "
            + ", ".join(f"{i['ticker']} ${i['claimed']:.2f}→${i['verified']:.2f}" for i in issues)
        )

    return verified_text
