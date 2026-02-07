"""Strategy Analysis Tool - Uses Opus 4.5 for deep investment analysis."""

import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Strategy aliases mapping to canonical names
STRATEGY_ALIASES = {
    # Warren Buffett
    "buffett": "buffett",
    "warren": "buffett",
    "value": "buffett",
    "value investing": "buffett",

    # Peter Lynch
    "lynch": "lynch",
    "peter": "lynch",
    "garp": "lynch",
    "growth": "lynch",

    # Ray Dalio
    "dalio": "dalio",
    "ray": "dalio",
    "macro": "dalio",
    "all weather": "dalio",

    # Benjamin Graham
    "graham": "graham",
    "ben": "graham",
    "benjamin": "graham",
    "deep value": "graham",

    # Cathie Wood
    "wood": "wood",
    "cathie": "wood",
    "ark": "wood",
    "innovation": "wood",
    "disruptive": "wood",
}

STRATEGY_NAMES = {
    "buffett": "Warren Buffett (Value Investing)",
    "lynch": "Peter Lynch (Growth at Reasonable Price)",
    "dalio": "Ray Dalio (Macro & Risk Management)",
    "graham": "Benjamin Graham (Deep Value)",
    "wood": "Cathie Wood (Disruptive Innovation)",
}

# Patterns to detect strategy analysis requests
ANALYSIS_PATTERNS = [
    # "analyze AAPL with buffett strategy"
    r"(?:analyze|analyse|evaluation?|assess)\s+([A-Z]{1,5})\s+(?:with|using|through|via)\s+(\w+)(?:\s+(?:strategy|style|approach|lens|framework))?",

    # "buffett analysis on AAPL" or "buffett analysis of AAPL"
    r"(\w+)\s+(?:analysis|evaluation|assessment)\s+(?:on|of|for)\s+([A-Z]{1,5})",

    # "should I buy AAPL? buffett" or "is AAPL a buy? (lynch)"
    r"(?:should\s+I\s+buy|is)\s+([A-Z]{1,5})\s+(?:a\s+)?(?:buy|good)?\??\s*[\(\[]?(\w+)[\)\]]?",

    # "AAPL buffett" or "AAPL lynch analysis"
    r"^([A-Z]{1,5})\s+(\w+)(?:\s+analysis)?$",

    # "what would buffett think of AAPL"
    r"what\s+would\s+(\w+)\s+(?:think|say)\s+(?:of|about)\s+([A-Z]{1,5})",
]


def detect_strategy_request(message: str) -> Optional[Tuple[str, str]]:
    """
    Detect if a message is a strategy analysis request.

    Returns:
        Tuple of (ticker, strategy) if detected, None otherwise
    """
    # Normalize message
    msg = message.strip()
    msg_upper = msg.upper()
    msg_lower = msg.lower()

    for pattern in ANALYSIS_PATTERNS:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            groups = match.groups()

            # Different patterns have ticker/strategy in different positions
            # Try to identify which is which
            for g1, g2 in [(groups[0], groups[1]), (groups[1], groups[0])]:
                g1_upper = g1.upper()
                g1_lower = g1.lower()
                g2_lower = g2.lower()

                # Check if g1 looks like a ticker (1-5 uppercase letters)
                is_ticker = bool(re.match(r'^[A-Z]{1,5}$', g1_upper))

                # Check if g2 is a known strategy
                strategy = STRATEGY_ALIASES.get(g2_lower)

                if is_ticker and strategy:
                    logger.info(f"Detected strategy request: {g1_upper} with {strategy}")
                    return (g1_upper, strategy)

                # Try the reverse
                strategy = STRATEGY_ALIASES.get(g1_lower)
                is_ticker = bool(re.match(r'^[A-Z]{1,5}$', g2.upper()))

                if is_ticker and strategy:
                    logger.info(f"Detected strategy request: {g2.upper()} with {strategy}")
                    return (g2.upper(), strategy)

    return None


def get_strategy_name(strategy_key: str) -> str:
    """Get the full display name for a strategy."""
    return STRATEGY_NAMES.get(strategy_key, strategy_key.title())


def get_strategy_analysis_prompt(ticker: str, strategy: str) -> str:
    """Get the detailed prompt for strategy analysis."""

    strategy_details = {
        "buffett": """
You are analyzing this stock through Warren Buffett's value investing lens.

KEY BUFFETT CRITERIA TO EVALUATE:

1. **Economic Moat** (Durable Competitive Advantage)
   - Does this company have pricing power?
   - What protects it from competition? (brand, network effects, switching costs, patents, cost advantages)
   - Is the moat widening or narrowing?

2. **Circle of Competence**
   - Is this a simple, understandable business?
   - Can you explain how it makes money in one paragraph?

3. **Management Quality**
   - Is management owner-oriented? (look at capital allocation history)
   - Insider ownership levels?
   - Track record of honest communication?

4. **Financial Strength**
   - Consistent earnings history (10+ years preferred)
   - Strong ROE (>15%) with low debt
   - Good free cash flow generation
   - Conservative balance sheet

5. **Valuation (Margin of Safety)**
   - Is the stock trading below intrinsic value?
   - What's a conservative estimate of intrinsic value?
   - Is there a margin of safety?

6. **Long-term Holding Potential**
   - Would you be comfortable holding this for 10+ years?
   - Is this a "wonderful company at a fair price" or a "fair company at a wonderful price"?
""",

        "lynch": """
You are analyzing this stock through Peter Lynch's GARP (Growth at Reasonable Price) lens.

KEY LYNCH CRITERIA TO EVALUATE:

1. **Stock Classification**
   - Slow Grower (2-4% growth, dividend focus)
   - Stalwart (10-12% growth, steady large cap)
   - Fast Grower (20%+ growth, smaller companies)
   - Cyclical (tied to economic cycles)
   - Turnaround (troubled company recovering)
   - Asset Play (hidden asset value)

2. **The Story**
   - Can you explain WHY this company will grow in one sentence?
   - Is the story playing out as expected?
   - Are there catalysts ahead?

3. **PEG Ratio Analysis**
   - P/E divided by growth rate
   - PEG < 1.0 is attractive
   - PEG < 0.5 is very attractive
   - Consider the quality of earnings growth

4. **Institutional Ownership**
   - Is Wall Street ignoring this stock? (positive)
   - Low analyst coverage can mean opportunity

5. **Insider Activity**
   - Are insiders buying? (very positive signal)
   - Management confidence in their own stock

6. **Ten-Bagger Potential**
   - Could this stock grow 10x from here?
   - What's the total addressable market?
   - Early or late in growth story?
""",

        "dalio": """
You are analyzing this stock through Ray Dalio's macro and risk management lens.

KEY DALIO CRITERIA TO EVALUATE:

1. **Economic Environment Assessment**
   - Where are we in the economic cycle?
   - Growth rising or falling?
   - Inflation rising or falling?
   - Which quadrant: Growth↑/Inflation↑, Growth↑/Inflation↓, Growth↓/Inflation↑, Growth↓/Inflation↓

2. **Asset Performance by Regime**
   - How does this stock/sector typically perform in current environment?
   - Historical performance during similar periods?

3. **Risk Analysis**
   - What could go wrong that the market isn't pricing in?
   - Tail risks to consider?
   - How correlated is this to other portfolio holdings?

4. **Diversification Contribution**
   - Does this add uncorrelated returns to a portfolio?
   - What's the risk contribution vs return contribution?

5. **Debt Cycle Positioning**
   - Where are we in the long-term debt cycle?
   - How leveraged is this company?
   - Interest rate sensitivity?

6. **Global Macro Factors**
   - Currency exposure?
   - Geopolitical risks?
   - Central bank policy impacts?
""",

        "graham": """
You are analyzing this stock through Benjamin Graham's deep value lens.

KEY GRAHAM CRITERIA TO EVALUATE:

1. **Quantitative Screens**
   - P/E ratio < 15 (or < industry average)
   - P/B ratio < 1.5 (ideally < 1.0)
   - Current ratio > 2.0
   - Debt/Equity < 0.5
   - Positive earnings for past 10 years
   - Dividend record (uninterrupted for 20 years ideal)

2. **Net-Net Analysis** (if applicable)
   - Net Current Asset Value = Current Assets - Total Liabilities
   - Trading below NCAV is rare but ideal
   - "Cigar butt" investing opportunity?

3. **Earnings Stability**
   - No earnings deficit in past 10 years
   - Earnings growth of at least 33% over 10 years
   - Consistency matters more than growth rate

4. **Margin of Safety**
   - How far below intrinsic value is the stock?
   - Graham wanted at least 33% discount
   - What's the downside protection?

5. **Mr. Market Perspective**
   - Is the market being irrational about this stock?
   - Fear or greed driving current price?
   - Opportunity from market overreaction?

6. **Conservative Valuation**
   - Graham's formula: Value = EPS × (8.5 + 2g)
   - Where g = expected 7-10 year growth rate
   - Compare to current price
""",

        "wood": """
You are analyzing this stock through Cathie Wood's disruptive innovation lens.

KEY WOOD/ARK CRITERIA TO EVALUATE:

1. **Disruptive Innovation Platform**
   - Is this company leading in one of these areas?
   - AI / Machine Learning
   - Robotics / Automation
   - Energy Storage / EVs
   - Genomics / Biotech
   - Blockchain / Fintech
   - Multi-omic sequencing

2. **Wright's Law Analysis**
   - Cost declines predictably with cumulative production
   - Is the company riding a cost curve?
   - What's the learning rate?

3. **Total Addressable Market (TAM)**
   - How big could this market become in 5 years?
   - Is the company's TAM expanding?
   - Market share trajectory?

4. **5-Year Time Horizon**
   - What's the expected stock price in 5 years?
   - Revenue growth trajectory?
   - Path to profitability (if not profitable)?

5. **Innovation Leadership**
   - Is management visionary?
   - R&D investment levels?
   - Patent portfolio and IP moat?

6. **Volatility Acceptance**
   - High volatility is expected for innovation stocks
   - Focus on long-term potential over short-term swings
   - Drawdown tolerance required
"""
    }

    return f"""Analyze **{ticker}** using the **{get_strategy_name(strategy)}** investment framework.

{strategy_details.get(strategy, "")}

Based on the data provided, give a comprehensive analysis and conclude with:

**VERDICT:** BUY / HOLD / PASS

**CONFIDENCE:** High / Medium / Low

**KEY FACTORS:**
- List the 3 most important factors driving your recommendation

**RISKS:**
- List the 2-3 main risks to watch

Keep your analysis thorough but readable. Use bullet points and bold headers for clarity.
Remember: This is educational analysis, not financial advice.
"""
