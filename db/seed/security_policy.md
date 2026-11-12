# Veridian Global Information Security Policy v4.2

## SEC-POL-089: Staging Bake Period for Production & Database Deployments
All production infrastructure changes, Elastic search cluster upgrades, major database migrations, or AWS production provisioning MUST undergo a minimum **14-day bake period in the staging environment** before being promoted to production. Direct deployment to AWS production without completing the 14-day staging soak test and security sign-off is strictly prohibited.

## SEC-POL-012: Confidential Data & Tenant Isolation
Customer PII, meeting transcripts, confidential merge requests, and cryptographic credentials must never be exposed in unencrypted storage or shared across organization boundaries. All multi-tenant tables enforce strict Row Level Security via `org_id`.

## SEC-POL-044: Credential Rotation & Signed Webhooks
All service-to-service webhooks and third-party callbacks (Slack, GitHub, internal media pipeline) must validate HMAC signatures using constant-time comparison and enforce timestamp replay windows.

