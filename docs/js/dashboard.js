// BigClaw Dashboard JavaScript

// Load data on page load
document.addEventListener('DOMContentLoaded', function() {
    loadPortfolioData();
    loadSentimentData();
    loadPerformanceChart();
    updateTimestamp();
});

// Update last updated timestamp
function updateTimestamp() {
    const el = document.getElementById('lastUpdate');
    fetch('data/metadata.json')
        .then(res => res.json())
        .then(data => {
            el.textContent = data.lastUpdate || 'Unknown';
        })
        .catch(() => {
            el.textContent = 'Data not yet available';
        });
}

// Load portfolio data
function loadPortfolioData() {
    const container = document.getElementById('portfolio-grid');

    fetch('data/portfolios.json')
        .then(res => res.json())
        .then(data => {
            container.innerHTML = '';

            data.portfolios.forEach(portfolio => {
                const changeClass = portfolio.totalReturn >= 0 ? 'positive' : 'negative';
                const changeSign = portfolio.totalReturn >= 0 ? '+' : '';

                let holdingsHtml = '';
                if (portfolio.holdings && portfolio.holdings.length > 0) {
                    holdingsHtml = `
                        <ul class="holdings-list">
                            ${portfolio.holdings.map(h => `
                                <li>
                                    <span class="ticker">${h.ticker}</span>
                                    <span class="shares">${h.shares} shares</span>
                                </li>
                            `).join('')}
                        </ul>
                    `;
                } else {
                    holdingsHtml = '<p class="no-holdings">No current holdings</p>';
                }

                container.innerHTML += `
                    <div class="portfolio-card">
                        <h3>${portfolio.name}</h3>
                        <p class="style">${portfolio.style}</p>
                        <div>
                            <span class="value">$${portfolio.totalValue.toLocaleString()}</span>
                            <span class="change ${changeClass}">${changeSign}${portfolio.totalReturn.toFixed(2)}%</span>
                        </div>
                        ${holdingsHtml}
                    </div>
                `;
            });
        })
        .catch(err => {
            container.innerHTML = '<p class="loading">Portfolio data not yet available. Check back after the morning report.</p>';
        });
}

// Load sentiment data
function loadSentimentData() {
    const container = document.getElementById('sentiment-data');

    fetch('data/sentiment.json')
        .then(res => res.json())
        .then(data => {
            container.innerHTML = '';

            data.tickers.forEach(item => {
                let sentimentClass = 'neutral';
                let label = 'Neutral';

                if (item.bullishPercent >= 60) {
                    sentimentClass = 'bullish';
                    label = 'Bullish';
                } else if (item.bullishPercent <= 40) {
                    sentimentClass = 'bearish';
                    label = 'Bearish';
                }

                container.innerHTML += `
                    <div class="sentiment-card">
                        <div class="ticker">${item.ticker}</div>
                        <div class="score ${sentimentClass}">${item.bullishPercent}%</div>
                        <div class="label">${label}</div>
                        <div class="source">via X/Twitter</div>
                    </div>
                `;
            });
        })
        .catch(err => {
            container.innerHTML = '<p class="loading">Sentiment data not yet available.</p>';
        });
}

// Load performance chart
function loadPerformanceChart() {
    const container = document.getElementById('performance-chart');

    // Check if chart image exists
    const img = new Image();
    img.onload = function() {
        container.innerHTML = `<img src="data/performance_chart.png" alt="Portfolio Performance Chart">`;
    };
    img.onerror = function() {
        container.innerHTML = '<p class="loading">Performance chart will be generated after the first trading day.</p>';
    };
    img.src = 'data/performance_chart.png';
}

// Utility function to format currency
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

// Auto-refresh every 5 minutes during market hours
function shouldAutoRefresh() {
    const now = new Date();
    const hour = now.getHours();
    const day = now.getDay();

    // Weekdays, 9 AM - 5 PM
    return day >= 1 && day <= 5 && hour >= 9 && hour < 17;
}

if (shouldAutoRefresh()) {
    setInterval(() => {
        loadPortfolioData();
        loadSentimentData();
        updateTimestamp();
    }, 5 * 60 * 1000); // 5 minutes
}
