from src.agent.event_log import get_payment_status, get_dispute_status, get_pending_promise

for inv_id in ["DEMO-0001", "DEMO-0003"]:
    print(inv_id, "paid:", get_payment_status(inv_id),
          "disputed:", get_dispute_status(inv_id),
          "pending_promise:", get_pending_promise(inv_id))