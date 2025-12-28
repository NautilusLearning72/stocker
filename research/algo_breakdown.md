Below is a **practical “builder’s view”** of major algo strategy families. For each one: **(1) overview, (2) realistic revenue expectations + how crowded it is, (3) execution requirements, (4) references, (5) scores**.

A quick framing first: **most discretionary/day-trading style approaches lose money after costs**, and only a small minority consistently win (this matters because many “algos” end up being automated day trading). ([Haas School of Business][1])
Also: **a large share of market volume is automated/algorithmic**, so many of the easiest edges are competed away. ([Greenwich][2])

---

## 1) Trend following / Time-series momentum (minutes→months)

### (1) Overview

Go **long** assets with positive trailing returns and **short/flat** those with negative trailing returns, usually with **volatility targeting** (size positions so portfolio risk stays stable). Works best on **liquid futures** (equity indices, rates, FX, commodities).

### (2) Revenue expectations + crowding

* **Best case (retail, disciplined, low fees):** “single-digit to mid-teens” annualised returns are *plausible* in strong trending regimes, but **multi-year drawdowns** happen.
* **Typical reality:** returns can look great in backtests; live results depend heavily on **costs, slippage, leverage discipline, and staying in the game during drawdowns**.
* **Crowding:** widely used by CTAs/managed futures; still persistent as a phenomenon across asset classes historically. ([ScienceDirect][3])

### (3) Execution (data + build)

* **Data:** daily or intraday OHLCV; for futures you also need **continuous contract rolls**.
* **Build:** signal engine (lookback windows), risk model (vol targeting), execution module (limit/market, roll logic), portfolio accounting + walk-forward backtests.

### (4) References

* Moskowitz, Ooi, Pedersen “Time Series Momentum” ([ScienceDirect][3])
* CFA Institute overview of trend/managed futures ([CFA Institute Research and Policy Center][4])

### (5) Scores (1=low, 5=high)

* Revenue expectation: **3/5**
* Implementation cost: **2/5**
* Operational cost: **2/5**
* Risks: **3/5** (drawdowns, whipsaws, leverage misuse)

---

## 2) Mean reversion (single-asset) + Pairs trading (stat arb)

### (1) Overview

* **Single-asset mean reversion:** bet that deviations from a short-term “fair value” revert (e.g., bands vs VWAP/SMA).
* **Pairs/stat-arb:** trade the **spread** between two related assets, entering when spread z-score is extreme and exiting on reversion.

### (2) Revenue expectations + crowding

* Classic academic pairs results looked strong historically, but in practice **edge is fragile** (regime breaks + costs). ([OUP Academic][5])
* **Crowding:** very crowded at funds; for retail, workable mainly if you find **niche universes** (sector/ETF constituents) and control costs.

### (3) Execution (data + build)

* **Data:** OHLCV at daily→minute; corporate actions (splits/dividends); borrow availability if shorting equities.
* **Build:** universe selection + stable hedging (OLS/cointegration), z-score engine, risk limits per pair, stop policies for regime breaks, execution with realistic slippage.

### (4) References

* Gatev, Goetzmann, Rouwenhorst (Pairs trading) ([OUP Academic][5])

### (5) Scores

* Revenue expectation: **2–3/5**
* Implementation cost: **3/5** (pair selection + risk handling is non-trivial)
* Operational cost: **2/5**
* Risks: **4/5** (correlation/cointegration breaks, short constraints)

---

## 3) Event-driven (earnings drift / PEAD, macro releases)

### (1) Overview

Trade systematic price behaviour after events:

* **PEAD:** stocks drift in the direction of the earnings surprise over weeks/months (historically).
* Macro: reaction/continuation after CPI/NFP etc. (harder; more crowded intraday).

### (2) Revenue expectations + crowding

* Academic surveys note historically meaningful abnormal returns, but many papers argue the effect has **weakened** as it became well-known. ([ScienceDirect][6])
* **Crowding:** high (quant + discretionary). Retail can still explore **small/mid caps**, but costs and fills matter.

### (3) Execution (data + build)

* **Data:** corporate events calendar, earnings surprise metrics (actual vs consensus), timestamps, price data around announcements.
* **Build:** event store, signal definitions (surprise deciles), delayed-entry logic, liquidity filters, compliance checks (avoid any non-public info), careful backtesting to avoid look-ahead bias.

### (4) References

* Review of PEAD + historical magnitude ([ScienceDirect][6])
* Bernard & Thomas (classic PEAD evidence) ([JSTOR][7])

### (5) Scores

* Revenue expectation: **2–3/5**
* Implementation cost: **3/5**
* Operational cost: **2–3/5** (event data pipelines)
* Risks: **3/5** (decay of edge, gap risk on earnings)

---

## 4) “Momentum” / cross-sectional factor strategies (rebalance weekly/monthly)

### (1) Overview

Rank assets (stocks/ETFs) by prior returns (or multi-factor signals) and hold winners vs losers, rebalancing periodically.

### (2) Revenue expectations + crowding

* Factor momentum is widely documented, but **transaction costs can materially reduce net returns**, especially with high turnover. ([Bank for International Settlements][8])
* **Crowding:** very high (ETFs, quant funds). Retail advantage mainly comes from **low fees + discipline**, not speed.

### (3) Execution

* **Data:** survivorship-bias-free price universe, corporate actions, (optional) fundamentals.
* **Build:** portfolio optimiser (constraints, turnover caps), realistic cost model, rebalancer, tax-aware logic (UK CGT context if relevant).

### (4) References

* BIS paper on currency momentum + cost sensitivity ([Bank for International Settlements][8])
* Discussion of implementation gap / turnover costs ([STOXX][9])

### (5) Scores

* Revenue expectation: **2–3/5**
* Implementation cost: **2/5**
* Operational cost: **1–2/5**
* Risks: **3/5** (crowding, crash risk, costs)

---

## 5) Market making / order-book (HFT / microstructure)

### (1) Overview

Earn the spread / rebates by posting bids/asks, managing inventory, and reacting to short-horizon order flow.

### (2) Revenue expectations + crowding

* This is where some of the **most profitable professional firms** operate, but they rely on **latency + infrastructure + access** retail usually doesn’t have. ([Bank for International Settlements][10])
* **Crowding:** extreme; dominated by specialist firms and exchanges’ microstructure.

### (3) Execution

* **Data:** level 2 order book, trades, tick data; exchange-specific market data; sometimes colocation.
* **Build:** ultra-low-latency stack, inventory/risk engine, exchange connectivity, robust kill-switches; heavy monitoring.

### (4) References

* BIS working paper on HFT “arms race” economics ([Bank for International Settlements][10])

### (5) Scores

* Revenue expectation: **1–2/5 (retail)**, **5/5 (professional with infra)**
* Implementation cost: **5/5**
* Operational cost: **5/5**
* Risks: **5/5** (technology, adverse selection, outages)

---

## 6) Volatility / options strategies (carry, breakouts, IV vs RV)

### (1) Overview

Trade volatility rather than direction:

* **Volatility breakout** (spot-only): enter when realised vol expands.
* **Options volatility**: sell/buy volatility when implied vs realised looks mispriced (but tail risk is real).

### (2) Revenue expectations + crowding

* **Selling vol** can look smooth until it doesn’t (crash risk).
* Crowded at funds; retail viability depends on **risk controls and option costs**.

### (3) Execution

* **Data:** options chains, implied vols/Greeks, realised vol estimates, dividends/rates.
* **Build:** options pricer/Greek engine, scenario stress tests, margin monitoring, event risk controls.

### (4) References

(If you want, I’ll pull a small curated reading list for options vol specifically based on the asset class you plan to trade.)

### (5) Scores

* Revenue expectation: **2–3/5**
* Implementation cost: **4/5**
* Operational cost: **3/5**
* Risks: **5/5** (tail risk, gap risk, liquidity)

---

# “How many people do this?” (practical reality)

* **A large portion of institutional equity flow is executed with algos/smart order routing.** ([Greenwich][2])
* Retail participation is growing in some regions, but regulators are actively tightening oversight in places (example: India’s SEBI rules for retail algo approval/audit trail). ([Reuters][11])
* Most “fast trading” profits are concentrated among specialist firms with infrastructure and risk controls. ([Financial Times][12])

---

# If you tell me 3 things, I’ll turn this into a concrete build plan + stack + first strategy

1. **Asset class**: UK/US equities, futures (CME), FX, crypto?
2. **Time horizon**: intraday, swing (days), medium-term (weeks)?
3. **Capital + constraints**: e.g., “£10k cash only, no leverage”, or “margin OK”.

If you don’t want to decide yet: the best “first build” for a solo developer is usually **trend following on liquid futures/ETFs** or **low-turnover mean reversion**, because the **infrastructure burden is reasonable** and the backtesting pitfalls are manageable.

[1]: https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trade%20040330.pdf?utm_source=chatgpt.com "Do Individual Day Traders Make Money? Evidence from Taiwan"
[2]: https://www.greenwich.com/press-release/electronic-platforms-capture-growing-share-us-equity-trading-volume?utm_source=chatgpt.com "US Equity Trading: Shift to Complex Market Structure"
[3]: https://www.sciencedirect.com/science/article/pii/S0304405X11002613?utm_source=chatgpt.com "Time series momentum"
[4]: https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/trend-following-with-managed-futures?utm_source=chatgpt.com "Trend Following with Managed Futures: The Search for ..."
[5]: https://academic.oup.com/rfs/article-abstract/19/3/797/1646694?utm_source=chatgpt.com "Pairs Trading: Performance of a Relative-Value Arbitrage Rule"
[6]: https://www.sciencedirect.com/science/article/pii/S2214635020303750?utm_source=chatgpt.com "A review of the Post-Earnings-Announcement Drift"
[7]: https://www.jstor.org/stable/2491062?utm_source=chatgpt.com "Post-Earnings-Announcement Drift: Delayed Price ..."
[8]: https://www.bis.org/publ/work366.pdf?utm_source=chatgpt.com "Currency Momentum Strategies"
[9]: https://stoxx.com/evaluating-the-true-cost-of-momentum-investing/?utm_source=chatgpt.com "Evaluating the true cost of momentum investing | Blog posts"
[10]: https://www.bis.org/publ/work955.pdf?ref=fufflix.ghost.io&utm_source=chatgpt.com "Quantifying the high-frequency trading \"arms race\""
[11]: https://www.reuters.com/world/india/india-markets-regulator-sets-track-trace-rules-retail-investors-algo-trading-2025-02-04/?utm_source=chatgpt.com "India markets regulator sets track and trace rules for retail investors' algo trading"
[12]: https://www.ft.com/content/54671865-4c7f-4692-a879-867ef68f0bde?utm_source=chatgpt.com "Jane Street is big. Like, really, really big"
