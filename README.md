# Fraud alerts with reasons · تنبيهات الاحتيال مع أسبابها

[![ci](https://github.com/aaturki/aie113-projects/actions/workflows/ci.yml/badge.svg)](https://github.com/aaturki/aie113-projects/actions/workflows/ci.yml)

**Turki Ahmed Alsulayyi (تركي أحمد الصليع)** — Software Engineering Practices for AI Systems, run
22–24 November 2026, SDAIA Academy (course code SDA-AIE-113).

The course's final project, fraud track, built individually (the workshop allows groups of
any size) with Claude Code as the coding agent. It starts from the workshop's starter repository
([snow10100/aie113-projects](https://github.com/snow10100/aie113-projects)), keeping only the
fraud track, and follows [GUIDE.md](GUIDE.md) stage by stage. **[JOURNAL.md](JOURNAL.md)**
holds one entry per stage: what we asked, what was built, what we checked and saw, and what
went wrong.

## What it does

One card payment goes in. Out come:
- a **fraud score** from 0 to 1;
- a **decision**:
  - **allow**, below 0.4;
  - **review**, from 0.4: the fraud team checks it;
  - **block**, from 0.9: the payment is stopped now and the fraud team is told;
- the **top three reasons**, for example "if V14 were typical, the score would fall from
  0.999 to 0.149".

It is a teaching service trained on two days of 2013 data. Never use it to block a card or
accuse anyone without a person checking.

On the 56,962 test payments it never learned from, it caught 56 of the 75 frauds (75%), and
86% of its alerts were real fraud, with 9 honest payments flagged. Always answering "not
fraud" scores 99.87% accuracy and catches nothing, which is why accuracy is not the measure.
The reorganised code reproduces all 62 answers saved in the workshop's notebook.

## Where each stage lives

| Stage | What | Where |
|---|---|---|
| 0 | The track and the model | [tracks/fraud/](tracks/fraud/), the notebook and its README |
| 1 | Clean architecture, and the notebook's answers kept | [src/fraud_alerts/](src/fraud_alerts/), [golden/notebook_answers.json](golden/notebook_answers.json) |
| 2 | The API (FastAPI) | [src/fraud_alerts/api/](src/fraud_alerts/api/), [payloads/](payloads/) |
| 3 | The container | [Dockerfile](Dockerfile), [compose.yaml](compose.yaml), [requirements.lock](requirements.lock) |
| 4 | The tests | [tests/](tests/), [scripts/smoke.py](scripts/smoke.py) |
| 5 | The pipeline, and branch protection | [.github/workflows/ci.yml](.github/workflows/ci.yml), [docs/blocked-pr.png](docs/blocked-pr.png) |
| 6 | Secrets | [config.py](src/fraud_alerts/config.py), [adapters/webhook.py](src/fraud_alerts/adapters/webhook.py), [compose.smoke.yaml](compose.smoke.yaml), [.pre-commit-config.yaml](.pre-commit-config.yaml), [docs/INCIDENT.md](docs/INCIDENT.md) |

## The layers

```
src/fraud_alerts/
  domain/     a payment, the allow/review/block rule, the reasons rule (no ML, no web)
  service/    the use case "assess one payment" and "announce a block"; what it needs (protocols)
  adapters/   the tools: the scikit-learn model bundle, the fraud team's webhook
  api/        the web entry point (FastAPI): contract, errors, logs, wiring
  config.py   every setting, read from FRAUD_ variables or secret files
  training/   the notebook's steps as a script, outside the layers, like the notebook
```

Imports only point inward (api → adapters → service → domain). A tool, `lint-imports`,
checks that on every change.

## Run it

You need Python 3.12; Docker is optional. These commands are for Windows PowerShell; on Linux
or macOS, activate with `source .venv/bin/activate` and use `export` instead of `$env:`.

```powershell
python -m venv .venv; .venv\Scripts\activate
pip install --no-deps -r requirements.lock      # the exact libraries the image runs
pip install -e ".[dev]"                         # the project and its tools
```

**The model** is never stored in git. Choose one:
- Train it yourself. The first run downloads the 150 MB data, then trains and compares every
  answer with the notebook:

  ```powershell
  $env:OMP_NUM_THREADS = "1"
  python -m fraud_alerts.training.train
  ```

- Or take the `model` artifact from the latest green
  [pipeline run](https://github.com/aaturki/aie113-projects/actions/workflows/ci.yml) and unzip
  it into `artifacts/`.

**Serve and try it:**

```powershell
python -m uvicorn fraud_alerts.api.app:create_app --factory --port 8000
```

Open http://localhost:8000/docs for the contract, or run, in a second window:

```powershell
curl.exe -s localhost:8000/v1/assess -H "content-type: application/json" -d "@payloads/flagged.json"
```

```powershell
python scripts/smoke.py http://localhost:8000
```

**Tests:** `python -m pytest -m "unit or integration"` runs the fast tests, in seconds, with a
stand-in model. `python -m pytest -m "model or data"` needs the trained model and the data.

**Container:** with the model in `artifacts/`, run `docker compose up --build --wait`. Or pull
the published image, `ghcr.io/aaturki/aie113-projects:main`.

## The pipeline

Every pull request and every push to main runs [ci.yml](.github/workflows/ci.yml):

| Job | What it does |
|---|---|
| secrets | gitleaks over every commit ever made |
| pre-commit | the developers' hooks, and a drill: a fake token must be stopped |
| lint | ruff, mypy in strict mode, and the layer rules |
| test | the fast tests, coverage at least 95% |
| model | trains on the real data and checks the notebook's 62 answers, the model and data tests, and a smoke test |
| image | builds the image, starts it with a pretend fraud team, runs the smoke test, and checks the image (not root, no secrets, Trivy) |
| publish | main only: pushes the image to GitHub's registry with a signed build record (OIDC, no stored key) |

`main` is protected. Changes arrive by pull request only, the first six jobs must pass, and
the rules apply to admins too. Pull request #1 shows a deliberately weaker model being stopped.

## The secret

The fraud team's webhook token is kept **encrypted inside the repository** with SOPS and age, in
[secrets/alert-webhook.enc.yaml](secrets/alert-webhook.enc.yaml). Only two private keys can open
it, and [.sops.yaml](.sops.yaml) lists their public halves: Turki's, on his laptop, and the
pipeline's, in the GitHub secret `SOPS_AGE_KEY`.

In the service, the token is a typed secret (`SecretStr`). It is read from the file
`/run/secrets/fraud_alert_webhook_token`, used in exactly one place, and masked in every log
line. The pipeline decrypts it with its own key and proves the whole path: it checks that the
token is in no log, no environment variable and not in the image. Secret scanning runs before
each commit, in the pipeline and on GitHub (push protection). To replace the token, run the
`rotate-practice-token` workflow. If a token or a key ever leaks, follow
[docs/INCIDENT.md](docs/INCIDENT.md).

## Limits

- **Old, narrow data.** The data covers two days, one card issuer, in 2013, and the V1 to V28
  inputs exist only in this dataset.
- **It misses some fraud.** About one fraud in four gets through.
- **The score is a ranking, not a promise.** 0.9 means "more suspicious than 0.5", not
  "90% sure".
- **The reasons name anonymous inputs.** They are honest, but mean nothing to a customer.
- **The hour is an assumption.** A payment's hour is read on the bank's clock, Riyadh by
  default: the model learned "night" from data that is only assumed to start at midnight.

---

<div dir="rtl" lang="ar">

## بالعربية

مشروع التخرج لورشة **ممارسات هندسة البرمجيات لأنظمة الذكاء الاصطناعي (SDA-AIE-113)** في أكاديمية
سدايا، مسار الاحتيال. أنجزه تركي منفردًا بمساعدة وكيل البرمجة Claude Code.

تدخل عملية بطاقة واحدة، فتخرج **درجة احتيال** من 0 إلى 1، و**قرار**:
- **سماح** تحت 0.4؛
- **مراجعة** من 0.4، يتحقق منها فريق الاحتيال؛
- **إيقاف** من 0.9، تتوقف العملية فورًا ويُبلَّغ الفريق.

ومعه **أهم ثلاثة أسباب** للتنبيه.

على 56,962 عملية لم يرها النموذج أثناء التعلّم، اكتشف 56 من أصل 75 عملية احتيال، وكانت 86% من
تنبيهاته احتيالًا حقيقيًا. ويعيد الكود الجديد جميع الإجابات الـ 62 المحفوظة في دفتر الورشة.

يشرح سجل المشروع [JOURNAL.md](JOURNAL.md) كل مرحلة: ما طلبناه من الوكيل، وما بُني، وكيف تحققنا
منه، وما تعثرنا فيه.

</div>
