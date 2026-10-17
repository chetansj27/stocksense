# StockSense demo script (3 minutes)

**Setup:** open the app, slider at 1.0. If the copilot is flaky, Overview / Purchase orders / Impact
work without Gemini, so the demo can continue.

1. **The problem (20s).** "Retailers either run out of what sells or tie up cash in what doesn't.
   Spreadsheet reorder rules ignore weekday patterns and growth."
2. **Overview (50s).** Point at the KPI tiles and the **Unusual demand** box: ice cream and sparkling
   water are up ~100% this week (a simulated heatwave). Show the risk table, pick Ice Cream, show actual vs
   forecast, click **Explain this recommendation**.
3. **What-if (30s).** Drag the slider to 1.3 ("a heatwave lifts demand 30%"). Stockouts and reorder
   spend change live.
4. **Copilot (50s).** Ask these three, in order:
   - "Which products will stock out first?"
   - "Why is demand unusual this week?"
   - "What happens if demand rises 20%?"
   - "Order what we need for the riskiest items."
5. **Customer side (40s).** Open the customer link (`<app-url>/?view=customer`) in a second tab. Ask "Do you have
   sparkling water?" (sold out, no restock date, offers substitutes) and "What can I get for a barbecue
   under $20?". Back on the manager view, the **Customer interest** box shows sparkling water asked for
   while out of stock. Create and approve a PO for it, then ask again as the customer: it now quotes a restock date.
6. **Human in the loop (20s).** Purchase orders tab: orders show product names and totals and are *pending*.
   Approve one, or use Approve all. CSV export and delete-all are available.
   "The AI proposes, a person approves."
7. **Impact (30s).** Impact tab: 60-day replay. Fill rate 95.5% to 99.6%, lost revenue $3.6k to $0.4k,
   at the cost of ~$1.1k more average inventory. Say the trade-off out loud.
8. **Close (10s).** BigQuery ML ARIMA_PLUS forecasting, Gemini agent with tools, Firestore orders,
   Cloud Run.

**Honest caveats if asked:** data is synthetic; the backtest compares against a rolling-average
rule, not against every possible baseline; orders are never sent to suppliers automatically.
