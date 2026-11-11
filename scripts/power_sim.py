"""Simulate the precision of the main-study error rates from the pilot (dev set) rates.

Pilot: 155 claims, 7 MISREPRESENTED (4.5%), 0 CONTRADICTED, 24 reports, 5 with at least one MISREPRESENTED claim (21%).
Simulated design: 60 announcements; reports per announcement = max(1, round(Exponential(mean 2.4)));
claims per report = max(1, int(Normal(6.5, 3))). The claim error probability varies by announcement:
Beta with mean p and intra-cluster correlation rho. 150 simulated studies per (p, rho), 400 bootstrap replicates each.
Output (stdout): mean and minimum number of error claims, and the mean width of the 95% announcement-cluster
bootstrap CI of the claim-level and report-level error rates.
"""
import random, statistics as st
def beta_params(m, rho):
    k = (1 - rho) / rho; return m * k, (1 - m) * k
def one(rng, p, rho, n_ann=60, B=400):
    a, b = beta_params(p, rho); anns = []
    for _ in range(n_ann):
        q = rng.betavariate(a, b); reps = []
        for _ in range(max(1, int(rng.expovariate(1/2.4) + 0.5))):
            n = max(1, int(rng.gauss(6.5, 3)))
            reps.append((n, sum(rng.random() < q for _ in range(n))))
        anns.append(reps)
    def est(S):
        c = sum(n for r in S for n, e in r); e = sum(e for r in S for n, e in r); rr = sum(1 for r in S for n, e in r); re_ = sum(1 for r in S for n, e in r if e)
        return e / c, re_ / rr, e
    pc, pr, ev = est(anns); bc, br = [], []
    for _ in range(B):
        S = [rng.choice(anns) for _ in anns]; x = est(S); bc.append(x[0]); br.append(x[1])
    bc.sort(); br.sort(); lo, hi = int(.025 * B), int(.975 * B) - 1
    return ev, bc[hi] - bc[lo], br[hi] - br[lo], pc
rng = random.Random(1)
print("p_claim  rho   events(mean,min)  claimCI_width  reportCI_width")
for p in (0.03, 0.045, 0.07):
    for rho in (0.05, 0.15):
        R = [one(rng, p, rho) for _ in range(150)]
        ev = [r[0] for r in R]
        print(f"{p:.3f}  {rho:.2f}   {st.mean(ev):5.1f},{min(ev):3d}        {st.mean(r[1] for r in R):.3f}          {st.mean(r[2] for r in R):.3f}")
