# OTP and editorial scheduler orchestration

## Purpose

The existing authenticated `POST /scheduler/run` endpoint is the single remote dispatch entry point for two independent queues:

1. OTP email outbox delivery, which is time-sensitive.
2. LinkedIn editorial publishing, which must preserve its existing one-publication-per-run semantics.

Local reminders, counters, calendar alerts, and other personal time-based behavior belong to the Android device and must not depend on this remote scheduler.

## Dispatch order and isolation

Each invocation performs:

1. Claim and process at most one OTP outbox item.
2. Run expired pending-signup cleanup.
3. Process at most one due LinkedIn publication using the existing scheduler and advisory lock.

Each subsystem is isolated. A failure in OTP delivery is logged and included in the response but does not prevent editorial publishing. A cleanup failure does not prevent either queue from running. An editorial failure does not undo a completed OTP delivery.

The OTP worker processes one item per invocation. This avoids claiming a sequential batch whose later jobs could lose their leases while earlier SMTP operations are still in progress. The worker's SMTP timeout is bounded by configuration; lease duration must remain longer than the maximum delivery operation.

## Scheduling and cost boundary

The currently documented Render Cronjob runs every 15 minutes and only the editorial queue was connected to it before this change. OTP challenges expire after 10 minutes, so the existing cadence cannot be the sole OTP delivery trigger.

This PR changes application dispatch code only. It does not change the Render Cronjob schedule, command, service, secrets, environment variables, SMTP credentials, provider, DNS, migrations in a persistent database, or production deployment.

A one-minute cadence is the next candidate for a controlled non-production measurement and rollout decision. The prior cost estimate for the existing 0.5 CPU / 512 MB Cronjob was approximately USD 1/month minimum service charge, subject to current Render pricing and measured runtime. No schedule change is authorized by this code change.

## Operational requirements before activation

- Confirm the current Render service still points to the expected branch and command.
- Verify the combined endpoint in a non-production environment with both queues populated.
- Test OTP delivery latency, expired challenge handling, retries, and worker overlap.
- Confirm an OTP failure cannot starve editorial publishing and vice versa.
- Measure execution duration and failure rates at the proposed cadence.
- Keep `AUTH_ROUTES_ENABLED=false` until authentication, origin/session transport, legal policy versions, and provider configuration are approved.
- Do not enable real SMTP delivery or change the Cronjob cadence without a separate rollout authorization.

## Verification status

The PR adds unit tests for dispatch order and failure isolation, plus the existing scheduler response regression test. GitHub Actions verification for this PR's exact HEAD must be confirmed before considering the code validated. No production change has been made.
