
export type ThresholdType = 'higherIsBetter' | 'lowerIsBetter' | 'range';

export interface MetricThreshold {
    type: ThresholdType;
    good: number; // Threshold for "good" (Green)
    bad: number;  // Threshold for "bad" (Red)
}

export const METRIC_THRESHOLDS: Record<string, MetricThreshold> = {
    // Valuation (Lower is generally better, except Yields)
    pe_ttm: { type: 'lowerIsBetter', good: 20, bad: 40 },
    pe_forward: { type: 'lowerIsBetter', good: 20, bad: 35 },
    peg_ratio: { type: 'lowerIsBetter', good: 1.0, bad: 2.5 },
    price_to_book: { type: 'lowerIsBetter', good: 3.0, bad: 10.0 }, // Tech/Growth bias can be higher
    price_to_sales: { type: 'lowerIsBetter', good: 5.0, bad: 15.0 },
    ev_to_ebitda: { type: 'lowerIsBetter', good: 15, bad: 30 },

    // Profitability (Higher is better)
    gross_margin: { type: 'higherIsBetter', good: 0.40, bad: 0.10 },
    operating_margin: { type: 'higherIsBetter', good: 0.15, bad: 0.05 },
    net_margin: { type: 'higherIsBetter', good: 0.10, bad: 0.0 },
    roe: { type: 'higherIsBetter', good: 0.15, bad: 0.05 },
    roa: { type: 'higherIsBetter', good: 0.05, bad: 0.0 },
    roic: { type: 'higherIsBetter', good: 0.10, bad: 0.05 },

    // Growth (Higher is better)
    revenue_growth_yoy: { type: 'higherIsBetter', good: 0.10, bad: 0.0 },
    earnings_growth_yoy: { type: 'higherIsBetter', good: 0.10, bad: 0.0 },
    eps_growth_yoy: { type: 'higherIsBetter', good: 0.10, bad: 0.0 },

    // Leverage (Lower is better, Ratios higher is better)
    debt_to_equity: { type: 'lowerIsBetter', good: 1.0, bad: 2.0 },
    net_debt_to_ebitda: { type: 'lowerIsBetter', good: 2.0, bad: 4.0 },
    current_ratio: { type: 'higherIsBetter', good: 1.5, bad: 1.0 },
    quick_ratio: { type: 'higherIsBetter', good: 1.0, bad: 0.8 },

    // Yields (Higher is better)
    dividend_yield: { type: 'higherIsBetter', good: 0.02, bad: 0.0 },
    fcf_yield: { type: 'higherIsBetter', good: 0.04, bad: 0.01 },

    // Market - usually neutral but Beta can be ranged
    beta: { type: 'range', good: 1.0, bad: 1.5 }, // 1.0 is neutral/good tracking. >1.5 volatile.
};
