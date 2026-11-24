# If the webhook token leaks: the incident plan

The fraud team's webhook token lets its holder send "payment blocked" alerts as if they came
from this service. A leaked token is an emergency even if nobody has used it yet, because
deleting it from where it leaked is not enough: copies remain (clones, forks, caches, logs).

**Who:** whoever finds the leak starts at step 1 at once and tells the fraud team's on-call
person. In this project that is Turki.

1. **Revoke it first (minutes).** Ask the fraud team to disable the leaked token on their side
   and issue a new one. From that moment the leaked copy is worthless.
2. **Replace it.** Put the new token where the service reads it: the platform's secret store,
   mounted as `/run/secrets/fraud_alert_webhook_token`. Restart the service and check
   `/v1/ready` (`alerts_to_fraud_team: true`) and one test alert.
3. **Check what happened while it was out.** Ask the fraud team for every alert received with
   the old token since the leak, and compare them with our log (by `trace_id`). An alert we
   did not send is a sign someone used it.
4. **Clean up where it leaked.** Delete the message, log or file that held it. If it reached a
   commit, removing it from history is optional, because the token is already dead (step 1);
   the secret scan will keep flagging it until the finding is recorded in `.gitleaksignore`
   with the date and the reason.
5. **Stop it happening again.** Find how it got out, then add the check that would have caught
   it: a scanner rule, a test, a log mask. Write down what happened and what changed.

The pipeline's practice token is made fresh for each run and thrown away with the runner, so
there is nothing to rotate for it.
