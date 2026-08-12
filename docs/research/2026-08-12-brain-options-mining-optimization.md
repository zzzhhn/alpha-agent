# BRAIN options mining optimization, RUN #66

## Observed failure

RUN #66 generated 20 expressions, selected and simulated five, and produced zero
submission-eligible alphas. This is not a self-correlation failure: every row was
rejected by BRAIN's in-sample gates before correlation was evaluated.

The measured pattern is informative:

- IV term was the strongest independent mechanism, but still only reached Sharpe
  0.75 and Fitness 0.47.
- Reversed IV momentum reached Sharpe -0.99. The specific direction was wrong.
- Rank-space VRP produced almost zero turnover and zero return, indicating that
  separately ranking realized and implied volatility erased useful magnitude.
- PCR dynamics and breakeven were positive but too weak to justify equal budget
  with the stronger mechanisms.
- The optional LLM logic screen failed to return usable scores, so shuffled
  mechanism order, rather than research evidence, decided the five simulations.

## Research interpretation

The academic evidence supports mechanisms, not random field permutations:

1. Bali and Hovakimian (2009) report a negative relation between expected stock
   returns and realized minus implied volatility. The implementation should
   therefore orient the signal as implied minus realized volatility, preserve the
   spread magnitude, and match tenors.
2. An, Ang, Bali, and Cakici (2014) find that increases in call IV predict higher
   stock returns while increases in put IV predict lower returns. Pooling call and
   mean IV and randomly reversing the result discards this directional structure.
3. Xing, Zhang, and Zhao (2010), plus Cremers and Weinbaum (2010), support the
   information content of volatility smirk and call-minus-put IV spread. That
   justifies retaining the proven skew signal as an anchor, but not replaying it
   unchanged when self-correlation is already saturated.
4. Fodor, Krieger, and Doran (2011) find predictive information in recent changes
   in call and put open interest. A short-horizon PCR change is a more faithful
   hypothesis than repeatedly z-scoring a 270-day PCR level.
5. Vasquez (2017) finds predictive information in IV term slope for option
   returns. Transfer to stock-return alpha is not guaranteed, so it remains a
   measured exploration mechanism rather than an assumed winner.

## Implemented search policy

For a five-simulation options round, the engine now prioritizes:

1. proven skew plus relative IV-term residual;
2. proven skew plus call-IV innovation;
3. standalone normalized IV-term slope;
4. call-IV innovation with pinned positive direction;
5. normalized IV-minus-historical-volatility spread.

PCR dynamics follows when the budget is larger. Plain skew, skew dynamics, and
breakeven remain available as controls or extended exploration, but cannot consume
the small budget merely because the generator shuffled them first.

The first pass uses a controlled TOP3000, delay-1, SUBINDUSTRY baseline. Random
liquidity wrapping and random settings variation are disabled for options motifs;
targeted near-miss retries remain available. This makes each expensive simulation
answer one interpretable question.

## Acceptance criteria for the next live round

The change is considered directionally successful if the next comparable options
round shows at least one of the following:

- one candidate clears BRAIN's in-sample gates and reaches the correlation stage;
- the best independent Sharpe materially improves beyond RUN #66's 0.75;
- the corrected call-IV innovation changes from the observed negative direction
  toward positive performance;
- VRP produces a non-degenerate return and turnover profile.

Passing is not guaranteed by construction. A live BRAIN round is the required
empirical acceptance test, and its outcomes should update future mechanism priors.

## Sources

- Bali, T. G., and Hovakimian, A. (2009), “Volatility Spreads and Expected Stock Returns,” Management Science. https://doi.org/10.1287/mnsc.1090.1063
- An, B.-J., Ang, A., Bali, T. G., and Cakici, N. (2014), “The Joint Cross Section of Stocks and Options,” Journal of Finance. https://doi.org/10.1111/jofi.12181
- Xing, Y., Zhang, X., and Zhao, R. (2010), “What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?” JFQA. https://doi.org/10.1017/S0022109010000220
- Cremers, M., and Weinbaum, D. (2010), “Deviations from Put-Call Parity and Stock Returns,” JFQA. https://doi.org/10.1017/S002210901000013X
- Fodor, A., Krieger, K., and Doran, J. S. (2011), “Do option open-interest changes foreshadow future equity returns?” Financial Markets and Portfolio Management. https://doi.org/10.1007/s11408-011-0164-z
- Vasquez, A. (2017), “Equity Volatility Term Structures and the Cross Section of Option Returns,” JFQA. https://doi.org/10.1017/S002210901700076X
