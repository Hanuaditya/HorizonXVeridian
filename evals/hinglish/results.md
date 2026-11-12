# Hinglish Sprint Utterance Evaluation Report

Evaluation of 12 synthetic code-mixed English/Hindi (Hinglish) sprint utterances on Horizon-Veridian's NLP extraction, assignee resolution, and compliance firewall.

## Summary Metrics

- **Total Utterances Tested:** 12
- **Task Action Extraction Accuracy:** **100.0%** (12/12)
- **Assignee Resolution Accuracy:** **100.0%** (12/12)
- **Compliance & Policy Firewall Accuracy:** **100.0%** (12/12)

## Detailed Evaluation Breakdown

| ID | Utterance (Hinglish) | Expected Assignee | Predicted Assignee | Task Extracted | Expected Flag | Predicted Flag | Status |
|---|---|---|---|---|---|---|---|
| `H-01` | Rohan, billing service mein Stripe webhook idempotency implement kar dena by Friday. | **Rohan Patel** | Rohan Patel | Yes | `CLEAN` | `CLEAN` | **PASS** |
| `H-02` | Priya, login page pe Google OAuth button render nahi ho raha hai, React frontend check kar lo. | **Priya Sen** | Priya Sen | Yes | `CLEAN` | `CLEAN` | **PASS** |
| `H-03` | Arjun, Elastic search cluster ko AWS production pe directly deploy karna hai, cost around 2.5 lakhs hoga. | **Arjun Rao** | Arjun Rao | Yes | `BUDGET_OR_LEAVE` | `BUDGET_OVERRUN | ON_LEAVE` | **PASS** |
| `H-04` | Rohan bhai, database query slow hai, index add karke latency optimize kar do. | **Rohan Patel** | Rohan Patel | Yes | `CLEAN` | `CLEAN` | **PASS** |
| `H-05` | Priya, hume Legacy v1 auth endpoints use karna padega frontend dashboard ke liye. | **Priya Sen** | Priya Sen | Yes | `BLOCKED_API` | `BLOCKED_API` | **PASS** |
| `H-06` | Arjun, backup script cron job setup kar dena production server pe. | **Arjun Rao** | Arjun Rao | Yes | `ON_LEAVE` | `ON_LEAVE` | **PASS** |
| `H-07` | Rohan, Kubernetes ingress controller mein TLS certificates renew karna hai. | **Rohan Patel** | Rohan Patel | Yes | `CLEAN` | `CLEAN` | **PASS** |
| `H-08` | Priya, sign-up flow mein password complexity validation add kar dena please. | **Priya Sen** | Priya Sen | Yes | `CLEAN` | `CLEAN` | **PASS** |
| `H-09` | Ek task hai jisme AWS compute budget 15 lakhs tak badhana padega next week. | **UNRESOLVED_ASSIGNEE** | UNRESOLVED_ASSIGNEE | Yes | `BUDGET_OVERRUN` | `BUDGET_OVERRUN` | **PASS** |
| `H-10` | Rohan, external Redis cluster connect karne ke liye VPC peering configure kar dena. | **Rohan Patel** | Rohan Patel | Yes | `CLEAN` | `CLEAN` | **PASS** |
| `H-11` | Priya, analytics tracking ke liye unapproved third-party tracking script inject kar do. | **Priya Sen** | Priya Sen | Yes | `SECURITY_POLICY_VIOLATION` | `SECURITY_POLICY_VIOLATION` | **PASS** |
| `H-12` | Arjun ko bolo paternity leave ke baad Kafka consumer lag reduce karne ka kaam dekhe. | **Arjun Rao** | Arjun Rao | Yes | `ON_LEAVE` | `ON_LEAVE` | **PASS** |
