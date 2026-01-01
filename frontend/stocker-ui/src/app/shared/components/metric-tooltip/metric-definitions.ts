export interface MetricDefinition {
  label: string;
  explanation: string;
  goodRange?: string;
}

export const METRIC_DEFINITIONS: Record<string, MetricDefinition> = {
  // Market & Valuation
  market_cap: {
    label: 'Market Cap',
    explanation:
      "Total market value of all shares. It's the company's size by market value. Large cap (>$10B), Mid cap ($2-10B), Small cap (<$2B).",
  },
  enterprise_value: {
    label: 'Enterprise Value',
    explanation:
      "Total company value including debt minus cash. More complete than market cap for comparing companies with different debt levels.",
  },
  shares_outstanding: {
    label: 'Shares Outstanding',
    explanation:
      'Total number of shares currently held by all shareholders. Used to calculate market cap and earnings per share.',
  },
  beta: {
    label: 'Beta',
    explanation:
      'Measures how much the stock moves compared to the overall market. Beta > 1 means more volatile than market, < 1 means less volatile.',
    goodRange: '0.8-1.2 for moderate risk',
  },

  // Valuation Ratios
  pe_ttm: {
    label: 'P/E Ratio (TTM)',
    explanation:
      'Price-to-Earnings over the trailing twelve months. Shows how much investors pay for each dollar of earnings. Lower may indicate undervaluation.',
    goodRange: '15-25 for most sectors',
  },
  pe_forward: {
    label: 'Forward P/E',
    explanation:
      'P/E based on estimated future earnings. Lower than TTM P/E suggests expected earnings growth.',
  },
  price_to_book: {
    label: 'Price/Book',
    explanation:
      "Compares stock price to the company's book value (assets minus liabilities). Below 1.0 may indicate undervaluation, but could also signal problems.",
    goodRange: '1-3 for most industries',
  },
  price_to_sales: {
    label: 'Price/Sales',
    explanation:
      'Stock price relative to revenue per share. Useful for evaluating companies that are not yet profitable.',
    goodRange: '1-2 is generally reasonable',
  },
  peg_ratio: {
    label: 'PEG Ratio',
    explanation:
      'P/E ratio divided by earnings growth rate. Accounts for growth - below 1.0 may indicate the stock is undervalued relative to its growth.',
    goodRange: 'Under 1.0 is attractive',
  },
  ev_to_ebitda: {
    label: 'EV/EBITDA',
    explanation:
      'Enterprise Value divided by earnings before interest, taxes, depreciation. A more complete valuation metric that accounts for debt.',
    goodRange: '8-12 for most sectors',
  },
  fcf_yield: {
    label: 'Free Cash Flow Yield',
    explanation:
      'Free cash flow per share divided by stock price. Higher yields indicate the company generates more cash relative to its price.',
    goodRange: '5%+ is generally good',
  },
  dividend_yield: {
    label: 'Dividend Yield',
    explanation:
      'Annual dividend payments as a percentage of stock price. Higher yields provide income but may indicate slow growth or risk.',
    goodRange: '2-6% for income stocks',
  },

  // Profitability
  gross_margin: {
    label: 'Gross Margin',
    explanation:
      'Revenue minus cost of goods sold, as a percentage. Shows how much money is left after direct costs to cover other expenses.',
    goodRange: 'Varies by industry; 40%+ is strong',
  },
  operating_margin: {
    label: 'Operating Margin',
    explanation:
      'Profit from operations as a percentage of revenue. Shows core business profitability before interest and taxes.',
    goodRange: '15%+ is generally healthy',
  },
  net_margin: {
    label: 'Net Profit Margin',
    explanation:
      'Net income as a percentage of revenue. The "bottom line" profitability after all expenses, taxes, and interest.',
    goodRange: '10%+ is good for most sectors',
  },
  roe: {
    label: 'Return on Equity (ROE)',
    explanation:
      'How efficiently the company uses shareholder equity to generate profits. Higher is better - shows management effectiveness.',
    goodRange: '15-20%+ is considered good',
  },
  roa: {
    label: 'Return on Assets (ROA)',
    explanation:
      'How efficiently the company uses its total assets to generate profits. Useful for comparing companies in the same industry.',
    goodRange: '5%+ depending on industry',
  },
  roic: {
    label: 'Return on Invested Capital',
    explanation:
      'Measures how well a company allocates capital to profitable investments. Should exceed the cost of capital to create value.',
    goodRange: 'Above cost of capital (8-12%+)',
  },

  // Growth
  revenue_growth_yoy: {
    label: 'Revenue Growth (YoY)',
    explanation:
      'Year-over-year revenue growth percentage. Positive growth indicates business expansion and increasing demand.',
  },
  earnings_growth_yoy: {
    label: 'Earnings Growth (YoY)',
    explanation:
      'Year-over-year earnings growth percentage. Shows improving profitability and operational efficiency.',
  },
  eps_growth_yoy: {
    label: 'EPS Growth (YoY)',
    explanation:
      'Year-over-year earnings per share growth. Accounts for share count changes unlike total earnings growth.',
  },

  // Leverage & Liquidity
  debt_to_equity: {
    label: 'Debt/Equity',
    explanation:
      'Total debt divided by shareholder equity. Higher ratios mean more financial risk and leverage. Very industry-dependent.',
    goodRange: 'Under 1.0 is conservative',
  },
  net_debt_to_ebitda: {
    label: 'Net Debt/EBITDA',
    explanation:
      'Net debt divided by earnings. Shows how many years of earnings would be needed to pay off debt. Lower is safer.',
    goodRange: 'Under 3.0 is generally safe',
  },
  current_ratio: {
    label: 'Current Ratio',
    explanation:
      'Current assets divided by current liabilities. Measures short-term liquidity and ability to pay near-term obligations.',
    goodRange: '1.5-3.0 is healthy',
  },
  quick_ratio: {
    label: 'Quick Ratio',
    explanation:
      'Like current ratio but excludes inventory. A more conservative liquidity measure for companies with slow-moving inventory.',
    goodRange: 'Above 1.0 is safe',
  },

  // Sentiment
  sentiment_score: {
    label: 'Sentiment Score',
    explanation:
      'Aggregate sentiment from news and social media, ranging from -1 (very negative) to +1 (very positive). 0 is neutral.',
  },
  sentiment_magnitude: {
    label: 'Sentiment Magnitude',
    explanation:
      'How strong or intense the sentiment is, regardless of direction. Higher magnitude means more emotional/opinionated coverage.',
  },
  article_count: {
    label: 'Article Count',
    explanation:
      'Number of articles analyzed for sentiment. More articles generally means more reliable sentiment data.',
  },
};
