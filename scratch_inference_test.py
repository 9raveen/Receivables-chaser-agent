from src.agent.bridge import invoice_to_state
from src.data.schema import Invoice
import json

with open("data/synthetic/demo_batch.json") as f:
    batch = json.load(f)

for rec in [batch[0], batch[2]]:
    inv = Invoice(**rec)
    state = invoice_to_state(inv)
    print(state["invoice_id"], "score:", state["propensity_score"],
          "tier:", state["risk_tier"], "overdue_ratio:", round(state["overdue_ratio"], 3))