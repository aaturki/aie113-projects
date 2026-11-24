# Project journal · سجل المشروع

**Group · المجموعة:** Turki, working alone (the workshop allows groups of any size). The AI
coding agent is Claude Code with Claude Opus 5.5. The agent drafted each entry from what it
ran and saw; Turki checks and edits every entry.
**Track · المسار:** fraud
**Repository · المستودع:** https://github.com/aaturki/aie113-projects

---

## Stage 0: Track and model · المسار والنموذج

**What we asked the agent · ما طلبناه من الوكيل**
Read AGENTS.md, GUIDE.md and tracks/fraud/README.md, explain the model in plain words, and keep
only the fraud track in this repository.

**What it built · ما بناه**
- Removed `tracks/stocks/` and `tracks/vision/`. Nothing else changed yet.

**What we checked, and what we saw · ما تحققنا منه وما رأيناه**
The agent read the notebook's code and the outputs saved in it:
- 284,807 card payments over two days, 492 of them fraud: about 1 in 580.
- Inputs: `V1` to `V28` (anonymous numbers the bank mixed from the real details), `Amount`,
  and the hour of the day made from `Time`. The answer it learns: `Class`, 1 for fraud.
- Split by time, never shuffled: training 170,884 payments (360 frauds, hours 0 to 33.4),
  validation 56,961 (57 frauds), test 56,962 (75 frauds).
- The model: gradient boosting, 300 small trees.
- The alert threshold 0.4 is chosen on the validation part by the fraud team's rule: at least
  8 of every 10 alerts must be real fraud (at 0.4: 51 alerts, 41 frauds).
- On the test part, which the model never saw: 65 alerts, 56 of the 75 frauds caught (74.7%),
  86.2% of alerts are real fraud, 9 honest payments flagged, average precision 0.789.
- Baselines: always answering "not fraud" is 99.87% accurate and catches nothing; the rule
  "alert above 1,000" raises 503 alerts and catches 2 frauds.
- The payment in the last cell scores 0.999. Its reasons: if V14 were typical the score would
  fall to 0.149, V10 to 0.278, V4 to 0.983.

Still to do by Turki: run the notebook in Colab (Runtime, Run all) and compare these numbers.

**What surprised us or went wrong · ما فاجأنا أو ما تعثرنا فيه**
Accuracy is useless here: a model that never alerts is 99.87% accurate. And the "big amount"
rule fails because most frauds in this data are small amounts.

**How we would explain this stage to a colleague · كيف نشرح هذه المرحلة لزميل**
The model gives each card payment a fraud score from 0 to 1. Above 0.4, the payment goes to
the fraud team with the three inputs that pushed the score up the most. It learned from the
first day and a half and was judged on the last hours, like a bank that learns from the past
and is tested on the future. It catches three frauds in four, and six alerts in seven are real
fraud. Because fraud is so rare, we judge it by those two questions, never by accuracy.

**Open questions · أسئلة ما زالت مفتوحة**
- The guide wants allow, review and block. The notebook has one threshold (review). A second,
  higher threshold for block is a business rule we must choose and justify.
- Where does the trained model live, if it may not go into git? (Stage 3.)
