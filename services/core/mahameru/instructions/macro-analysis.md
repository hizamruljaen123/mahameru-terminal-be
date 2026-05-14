# Macro Analysis Instructions

Apply these rules when analyzing macroeconomic trends, cross-market correlations, or regime detection.

## Yield Curve Analysis

### Curve Shape Interpretation
```
Normal (Upward sloping): Economic expansion expected
Flat: Transition or uncertainty
Inverted: Recession signal (2Y-10Y spread < 0)
Humped: Rare, often transitory
```

### Key Spread Monitoring
```
2Y-10Y Spread: Primary recession predictor
3M-10Y Spread: Alternative signal, earlier indicator
5Y-30Y Spread: Inflation expectation signal
```

### Historical Patterns
- 2Y-10Y inverted 6+ months ahead: 70% recession probability
- Inversion followed by steepening: Typically soft landing
- Rapid flattening: Market stress signal

## Hidden Markov Model (HMM) Regime Detection

### Regime Classification
```
REGIME 0 - Risk-Off / Deflation
  - High VIX, low S&P
  - USD strength, JPY strength
  - Bond rally, gold rally
  - Correlated with: Crisis, Fed pivot

REGIME 1 - Risk-On / Growth
  - Low VIX, S&P highs
  - EM strength, commodity strength
  - Equity bull, credit tight
  - Correlated with: Expansion, earnings growth

REGIME 2 - Stagflation / Uncertainty
  - Mixed signals, volatility
  - Dollar strength, commodity mixed
  - Defensive equity, inflation pricing
  - Correlated with: Supply shocks, policy uncertainty

REGIME 3 - Reflation / Policy Response
  - Central bank active
  - Bond volatility, credit expansion
  - Risk asset recovery
  - Correlated with: Post-crisis, policy shifts
```

## Cross-Asset Correlation Matrix

### Typical Correlations (Normal Environment)
```
S&P 500 ↔ Treasury: -0.3 to -0.5 (negative)
S&P 500 ↔ Gold: -0.2 to -0.4 (negative)
S&P 500 ↔ USD: -0.4 to -0.6 (negative)
USD ↔ EM: -0.6 to -0.8 (strong negative)
Gold ↔ Real Rates: -0.7 to -0.9 (strong negative)
```

### Breakdowns (Regime Transitions)
- Equity-bond correlation turning positive: Inflation regime
- Gold-dollar correlation turning positive: System stress
- EM-USD correlation weakening: Dollar strength plateau

## Indonesian Macro Context

### Key Indicators
```
BI Rate: Policy rate, direct impact on banking NIM
CPI: Inflation, guides BI policy
IIP: Investment balance, current account health
Rupiah: IDR/USD, impacts import costs and export competitiveness
```

### Critical Levels
```
USD/IDR < 14,000: Strong rupiah, import-friendly
USD/IDR 14,000-15,000: Normal range
USD/IDR > 15,000: Weak rupiah, inflationary
USD/IDR > 16,000: Crisis level, policy intervention likely
```

## Leading vs Lagging Indicators

### Leading (Predict Future)
- 10Y Treasury Yield: Economic outlook
- Credit Spreads (HY): Risk appetite
- PMI: Future economic activity
- Building Permits: Future construction
- Initial Jobless Claims: Employment trends

### Lagging (Confirm Past)
- Unemployment Rate: Past employment
- CPI: Past inflation
- GDP: Past output
- Industrial Production: Past manufacturing

## Risk Analysis Framework

### Step 1: Identify Current Regime
- Apply HMM model to recent data
- Check yield curve shape
- Assess cross-asset correlations

### Step 2: Map Regime to Asset Behavior
- Adjust expectations based on regime
- Identify regime-breakdown signals

### Step 3: Position for Regime Change
- Monitor leading indicators for shift
- Scale positions as confidence increases
- Set stops at regime-breakdown levels

## Global Macro Events to Monitor

1. **Fed Meeting**: Rate decisions, QT signals
2. **US CPI**: Inflation trajectory
3. **China PMI**: Global growth engine
4. **EUR/USD**: Dollar direction
5. **VIX**: Risk appetite thermometer
6. **Copper**: Industrial demand proxy
7. **Gold**: Real rate sensitivity
8. **EM Flows**: Risk-on/off measurement