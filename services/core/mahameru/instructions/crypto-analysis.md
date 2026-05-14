# Cryptocurrency Analysis Instructions

Apply these rules when analyzing crypto markets, on-chain metrics, or digital asset trends.

## On-Chain Metrics Framework

### Network Health Indicators
```
Transaction Count: Daily active addresses, transaction volume
Fees: Network demand indicator (high fees = high demand)
Hash Rate: Network security and mining economics (BTC)
Active Addresses: User adoption proxy
```

### Exchange Flow Analysis
```
Deposit to Exchange: Potential selling pressure
Withdrawal from Exchange: Potential accumulation
Exchange Balance: Supply available for sale
Stablecoin Flow: Tether/USDC movement indicates sentiment
```

### Holder Behavior
```
Exchange → Cold Storage: HODLing signal
Young Coins Moving: Profit-taking or distribution
Long-Term Holder Supply: Decreasing = distribution risk
New Addresses: Onboarding indicator
```

## Funding Rate Interpretation

### Rate Classification
```
Funding > 0.1% per 8h: Extreme bullish, CRITICAL warning
Funding 0.03-0.1% per 8h: Bullish, elevated leverage
Funding -0.03% to 0.03%: Neutral, balanced market
Funding -0.03 to -0.1% per 8h: Bearish, elevated shorting
Funding < -0.1% per 8h: Extreme bearish, CRITICAL warning
```

### Funding Rate Strategy
- Funding > 0.1%: Consider reducing long positions
- Funding < -0.1%: Consider reducing short positions
- Funding crossing zero: Trend reversal potential

## Whale Activity Detection

### Transaction Size Classification
```
Whale: > $1M USD equivalent
Mega Whale: > $10M USD equivalent
Shark: $100K - $1M USD equivalent
Minnow: < $100K USD equivalent
```

### Behavioral Signals
```
Whale Accumulation: Large inflow to cold storage, price stable/rising
Whale Distribution: Large inflow to exchange, price falling
Whale Support: Price dips bought aggressively
Whale Resistance: Price rallies sold aggressively
```

## Market Structure Analysis

### Trend Identification
```
Higher High + Higher Low: Uptrend intact
Lower High + Lower Low: Downtrend intact
Lower High + Higher Low: Compression, breakout pending
Higher High + Lower Low: Distribution, breakdown pending
```

### Volume Profile
```
Rising Price + Rising Volume: Strong trend
Falling Price + Rising Volume: Strong trend continuation
Rising Price + Falling Volume: Weak trend, reversal risk
Falling Price + Falling Volume: Trend exhaustion
```

## Exchange-Specific Metrics

### Binance Metrics
- Open Interest: Total derivatives positions
- Long/Short Ratio: Trader positioning
- Funding Rate: 8-hour rate across contracts

### Glassnode Indicators
- SOPR (Spent Output Profit Ratio): Realized profit/loss
- MVRV: Market Value vs Realized Value
- SOPR > 1: Profit taking; < 1: Accumulation

## Risk Management

### Position Sizing
```
High Funding (>0.1%): Max 25% normal size
Neutral: Normal position size
Low Funding (<-0.1%): Max 25% normal size
```

### Stop Loss Guidelines
- Major support/resistance ±2%
- Funding rate extreme: Tight stops
- Whale accumulation zone: Wider stops

## Indonesian Crypto Context

- IDR crypto pairs on major exchanges (Tokocrypto, Binance ID)
- Telegram groups as sentiment indicators
- Regulatory uncertainty: Bappebti oversight
- Community-driven narratives often dominate

## Data Sources

1. On-chain: Glassnode, CryptoQuant, Nansen
2. Funding rates: Binance, Bybit, OKX
3. Social: LunarCrush, Santiment
4. Orderbook: Exchange APIs for liquidity analysis