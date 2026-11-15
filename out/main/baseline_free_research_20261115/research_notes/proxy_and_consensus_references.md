# Proxy references, model populations, and self-consistency as substitutes for a missing base model

Retrieval status. Each source below was located by search in this session (2026-11-14). Claims come from the abstract page, the search result text, or the publisher record I read. Sources marked "(id confirmed; content from prior knowledge)" had their id checked but their content was not reread this session. Sources marked "(not retrieved this session)" rest on prior knowledge only and should be checked before they are cited in the paper. Our setting is described in the brief: matched prompts that differ only in the supported candidate, an LLM judge scoring about 100 binary axes, 16 samples per candidate x instruction x axis cell, stored reply texts and embeddings, and a registered test that subtracts the untuned base model's one-vs-rest gaps (paired max-|t| permutation test).

## 1. Proxy baselines: how much are generic name effects shared across models, and when does subtracting a proxy help or hurt?

### Takeaway
Studies that run many LLMs on the same name-substitution prompts find that the direction of generic name effects is often shared (all 22 models in one hiring audit favor female names; 16 of 18 models pick Biden in every run). Magnitudes and dominant drivers are model-specific, family signatures diverge, and post-training changes the effects, so base and tuned versions of one model differ. I found no study that reports a cell-level cross-model correlation of name effects. That correlation decides whether subtracting a proxy reduces or inflates the nuisance, so the literature cannot settle the paper's claim either way, and our own stored bases could.

### Cited Findings
- Rozado tested 22 LLMs on gender-swapped resume pairs across 70 professions. Every model leaned toward female-named candidates with identical qualifications: 56.9% vs 43.1% selection, Cohen's h = 0.28. Replacing names with "Candidate A"/"Candidate B" and counterbalancing gave parity, so the effect tracks the name cue. 21 of 22 models also had a significant first-position preference (63.5% vs 36.5%) ([Rozado, arXiv 2505.17049](https://arxiv.org/abs/2505.17049)).
- Potter et al. ran 18 open and closed models 100 times each on a 2024 US presidential vote. 16 of 18 chose Biden every time. Base models voted Biden less often than their instruction-tuned versions, and the authors suggest post-training amplified the lean ([Potter et al., EMNLP 2024, arXiv 2410.24190](https://arxiv.org/abs/2410.24190); [ACL Anthology](https://aclanthology.org/2024.emnlp-main.244)).
- Haim, Salinas and Nyarko report qualitatively similar name-based race and gender disparities across GPT-4, GPT-3.5 and PaLM-2 on the same advice prompts ([Haim et al., arXiv 2402.14875](https://arxiv.org/abs/2402.14875)).
- Bhetwal, Mert and Whitehouse ran 6 local LLMs from several providers and sizes on a fill-in-the-blank name choice task, with 300,000 responses. They find consistent, measurable bias: models prefer names that are less stereotypically male, older, popular, and white. Gender is the strongest factor, then age, popularity and race. The HTML version's text, as returned by search, adds that magnitude and dominant drivers are model-specific ([Bhetwal et al., arXiv 2610.22053](https://arxiv.org/abs/2610.22053); [HTML](https://arxiv.org/html/2610.22053v1)).
- Jeong, Ma and Houmansadr treat fairness as a relation between models (Bias Similarity Measurement). The v4 abstract covers 30 LLMs and over one million prompts. It reports that instruction tuning "primarily enforces abstention rather than altering internal representations", that family signatures diverge (Gemma favors refusal, LLaMA 3.1 approaches neutrality), and that open-weight models can match proprietary ones. It proposes the method for lineage screening. v2 (13 LLMs, five families) said fine-tuning had little effect on output distributions ([Jeong et al., arXiv 2410.12010](https://arxiv.org/abs/2410.12010v4); [v2](https://arxiv.org/html/2410.12010v2)).
- Eloundou et al. measure "first-person fairness" counterfactually over two genders and four races in six of OpenAI's models. They report that "post-training reinforcement learning techniques significantly mitigate these biases" ([Eloundou et al., ICLR 2025, arXiv 2410.19803](https://arxiv.org/abs/2410.19803)).
- Perez et al. report that larger LMs repeat back a dialog user's preferred answer (sycophancy) and that RLHF makes LMs express stronger political views on gun rights and immigration ([Perez et al., arXiv 2212.09251](https://arxiv.org/abs/2212.09251)).
- Itzhak et al. find that instruction-tuned models (Flan-T5, Mistral-Instruct, GPT-3.5, GPT-4) show more decoy, certainty and belief bias than their pretrained counterparts ([Itzhak et al., arXiv 2308.00225](https://arxiv.org/abs/2308.00225)). A 2025 follow-up by the same group argues the biases mainly originate in pretraining and that instruction tuning plays a smaller role ([review page for "Planted in Pretraining, Swayed by Finetuning"](https://liner.com/review/planted-in-pretraining-swayed-by-finetuning-case-study-on-origins)). The Salamandra report finds smaller primacy, recency and majority-class effects in instructed models than in their bases ([arXiv 2502.08489](https://arxiv.org/abs/2502.08489)). These results conflict on whether tuning grows or shrinks a given bias.
- Kim, Garg, Peng and Garg find that when two models are both wrong on one leaderboard dataset, they agree on about 60% of those items. Correlation is higher for models sharing a provider or architecture, and larger, more accurate models have highly correlated errors even across providers ([Kim et al., ICML 2025, arXiv 2506.07962](https://arxiv.org/abs/2506.07962)). Goel et al. report that model mistakes become more similar as capability increases ([Goel et al., arXiv 2502.04313](https://arxiv.org/abs/2502.04313)).
- ICE-Guard tests 3,000 vignettes on 11 LLMs from 8 families with single-attribute swaps. The mean demographic (name and race swap) flip rate is 2.2%, below authority (5.8%) and framing (5.0%). The abstract page gives no per-model demographic rates and no significance test ([Basu and Chakraborty, arXiv 2603.18530](https://arxiv.org/abs/2603.18530)).
- Membership inference gives the closest methodological parallel. Attacks that calibrate against a reference model are "highly fragile" to the distribution the reference was trained on. Comparing the target against its own perturbed neighbours outperforms the reference-based LiRA by up to 100% under realistic data assumptions ([Mattern et al., Findings of ACL 2023, arXiv 2305.18462](https://arxiv.org/abs/2305.18462); [ACL Anthology](https://aclanthology.org/2023.findings-acl.719)).
- In psychometrics, Wang, Liu and Liu define DIF as item-specific residuals from a regression fitted to item parameters across groups. A robust regression estimator keeps false alarms controlled when DIF and non-DIF items are mixed ([Wang, Liu and Liu, J. Educ. Behav. Stat. 47(6):666-692, 2022](https://econpapers.repec.org/RePEc:sae:jedbes:v:47:y:2022:i:6:p:666-692)). This is the scaled analogue of proxy subtraction.

### Inferences
- Write the target's one-vs-rest gap in a cell as g_T = d + n_T + e_T, with d the trained differential treatment, n_T the generic name effect and e_T sampling error. A proxy gives g_P = n_P + e_P. Raw subtraction lowers the nuisance variance only if Var(n_T - n_P) < Var(n_T), that is if Cov(n_T, n_P) > Var(n_P)/2. With equal variances this means the cell-level cross-model correlation of name effects must exceed 0.5. Below that, subtracting a proxy makes the null noisier than no subtraction at all. Any magnitude difference also leaves a mean residual that the permutation null does not model, so the test rejects on untuned targets.
- Scaled subtraction g_T - beta*g_P with beta = Cov/Var always reduces nuisance variance when the correlation is nonzero. Beta must be estimated across cells, though, and the estimate absorbs d unless d is sparse. Robust regression across cells (the Wang, Liu and Liu construction) handles a sparse d only.
- The cross-model evidence is mostly direction-level (share of models favoring a group). Shared direction with model-specific magnitude is the case where a proxy cancels the sign and leaves residuals of unknown sign and size. The literature therefore supports "a different model is an unreliable baseline". It does not support "a different model cannot serve as a baseline" without our own measurement.
- Post-training changes the very effects we subtract (Potter, Eloundou, Itzhak). A tuned model from another vendor as proxy confounds "has a different post-training recipe" with "has a covert objective". An untuned base from the same family is the least bad proxy. Size differences still matter, since sycophancy grows with scale (Perez).
- An experiment on stored data would turn the claim into a result. For each pair of stored untuned bases A and B, run the registered test on base A using base B as the reference. The rejection rate is the false-positive rate of proxy subtraction. Also report the cell-level correlation of one-vs-rest gaps between bases, against the 0.5 threshold above. This needs only that the bases were sampled on identical prompts, candidates, instructions and judge. I did not check the code repo to confirm that.

### Gaps
- I found no paper that reports a prompt x name (cell-level) correlation of identity effects between models. Evidence is aggregate or direction-level.
- I did not read the per-model tables of Haim et al., Rozado, Bhetwal et al. or ICE-Guard. The per-model spread of name effects therefore comes from abstract-level statements only.
- Perez et al.'s abstract does not say whether sycophancy appears in pretrained models without RLHF. My recollection is that the full paper shows it does, but I did not verify this.
- The arXiv id of the 2025 Itzhak et al. follow-up was not confirmed.
- I found no audit that uses another model's group effects as the subtracted baseline. This appears unstudied.

## 2. Multi-model consensus: can a population of models serve as the reference, and has anyone tested whether one LLM is an outlier for one group?

### Takeaway
A population of models as reference is established in backdoor detection (meta-classifiers over model zoos) and in model-equality testing, and 2026 benchmark work applies DIF across model families. I found no LLM paper that tests whether one model is an outlier in a group effect against a population. Consensus can only flag idiosyncratic differential treatment. A bias shared across the population (common in identity bias) is absorbed into the reference. Correlated behavior across models also makes the population less informative than its head count suggests.

### Cited Findings
- Universal Litmus Patterns feed a few optimized inputs to a network and classify it as clean or backdoored from the outputs. The classifier is trained over a population of clean and trojaned networks, needs no training data, and was tested on thousands of networks on GTSRB, MNIST and CIFAR10 ([Kolouri et al., CVPR 2020, arXiv 1906.10842](https://arxiv.org/abs/1906.10842)). Meta Neural Trojan Detection uses the same population-of-models design (Xu et al., [arXiv 1910.03137](https://arxiv.org/abs/1910.03137); not retrieved this session).
- Model equality testing frames "is this API serving the claimed model" as a two-sample MMD test against a reference distribution (released weights or an earlier API version). A Hamming-type string kernel had median power of 77.4% against a range of distortions with about 10 samples per prompt. 11 of 31 Llama endpoints audited in summer 2024 served distributions different from Meta's weights ([Gao, Liang and Guestrin, ICLR 2025, arXiv 2410.20247](https://arxiv.org/abs/2410.20247)).
- A NeurIPS 2026 paper applies Mantel-Haenszel DIF to six LLM benchmarks with model families (Llama, Qwen) as groups. Many items behave differently across families even among models with equal total scores. Flagged items concentrate in benchmark categories such as subjects and subtasks ([NeurIPS 2026 poster 139203](https://neurips.cc/virtual/2026/poster/139203); arXiv id not found).
- Zheng and Yang use cross-family DIF to test leaderboard robustness. In four of five benchmarks, 30.9% to 47.1% of cross-family pairs within one point reverse order ([NeurIPS 2026](https://neurips.cc/virtual/2026/178380)).
- Population-shared biases are common. 16 of 18 models favor Biden ([arXiv 2410.24190](https://arxiv.org/abs/2410.24190)), and all 22 models favor female-named candidates ([arXiv 2505.17049](https://arxiv.org/abs/2505.17049)).
- Model behaviors are dependent. Errors correlate within provider and architecture and across providers for strong models ([arXiv 2506.07962](https://arxiv.org/abs/2506.07962)). A 2026 paper argues that agreement among LLM judges overstates evidence because their errors are not independent, with stronger dependence among frontier judges even across providers ([Hossain, Yousefi and Lim, arXiv 2609.22512](https://arxiv.org/abs/2609.22512)).
- Bias Similarity Measurement proposes relational, cross-model fairness auditing for regression testing and lineage screening over 30 models ([arXiv 2410.12010](https://arxiv.org/abs/2410.12010v4)).

### Inferences
- The null is that the target's group-effect statistic is exchangeable with those of K reference models. A rank-based p value is at least 1/(K+1), so one target and one statistic need K >= 19 reference models to reach p <= 0.05. Per-cell inference needs a parametric model instead, such as a random-effects meta-analysis with between-model variance tau^2 and a studentized deleted residual for the target.
- Exchangeability fails for benign reasons: size, vendor, and post-training recipe all shift name effects. A rejection shows the target is atypical for this group. It does not show a trained objective.
- Correlated behavior shrinks the effective population. Ten models from three families may carry the information of a few independent models.
- For the Transluce user-awareness replication on served models, where no base exists, a population of served models is the only available reference. A rejection there claims "this model's user-awareness is atypical among served models", nothing about how it arose.
- DIF with models as groups (as in the NeurIPS 2026 work) is the same consensus test in psychometric form: items = candidate x instruction x axis cells, matching on each model's overall rate.
- Fit: the few targets and bases we store make too small a population for inference, though they can be shown descriptively. A real consensus test needs new sampling of many models on the same matched prompts with the same judge.

### Gaps
- I found no LLM paper that runs a meta-analytic or rank-based outlier test of one model's group effect against a model population.
- I did not reread the MNTD paper this session.

## 3. Psychometric DIF as a framework: items, groups, and how the reference is chosen without a control

### Takeaway
DIF gives a clean vocabulary: items are instruction x axis cells, the groups are candidates (or models), and the matching variable is overall propensity. Its central lesson is an identification result. Without a known DIF-free anchor, only relative DIF between items is identified (Bechger and Maris). Anchor-free methods recover absolute DIF only by assuming fewer than half the items carry DIF (Halpin) or a minimal-L1 sparsity condition (Chen et al.). Generic name effects in LLMs are dense, so these assumptions fail exactly where we need them. DIF does separate a uniform group shift ("impact") from item-specific effects, which naive group-vs-group tests conflate.

### Cited Findings
- Holland and Thayer introduced the Mantel-Haenszel DIF procedure, which stratifies examinees on total score and tests a common odds ratio across strata ([ETS Research Report RR-86-31, DOI 10.1002/j.2330-8516.1986.tb00186.x](https://www.ets.org/research/policy_research_reports/publications/report/1986/hwnk.html)). Catalogs disagree on the report number (86-31 vs 86-69) ([rasch.org](https://rasch.org/rmt/rmt32a.htm)).
- Swaminathan and Rogers proposed logistic-regression DIF with total score as a covariate and a Wald test. It is more powerful than MH for nonuniform DIF and as powerful for uniform DIF ([J. Educ. Meas. 27(4):361-370, 1990, DOI 10.1111/j.1745-3984.1990.tb00754.x](https://doi.org/10.1111/j.1745-3984.1990.tb00754.x)).
- Bechger and Maris argue that an item's absolute difficulty is not identified from the data, while relative difficulties of item pairs are. They define DIF through item-pair relative difficulties and give a Wald test of their invariance across groups that does not depend on the chosen normalization. It is implemented, as an exploratory tool, in the dexter R package ([Psychometrika 80(2):317-340, 2015, DOI 10.1007/s11336-014-9408-y](https://doi.org/10.1007/s11336-014-9408-y); [dexter DIF vignette](https://cran.r-project.org/web/packages/dexter/vignettes/DIF_vignette.html)).
- Halpin treats DIF as outlier detection in IRT scaling and uses a redescending M-estimator tuned to a target Type I error rate. Its finite-sample breakdown point is 1/2: the estimate stays bounded whenever fewer than half the items have DIF. He argues that anchor-based tests are unsatisfying because they proceed as if the anchors were known a priori. The paper covers the 2PL model with two independent groups ([Halpin, arXiv 2207.04598](https://arxiv.org/abs/2207.04598v4)).
- Chen, Li, Ouyang and Xu give DIF inference without known anchors under a MIMIC model, with valid confidence intervals and p values and control of Type I error and FDR. Identification uses a minimal L1-norm condition, and they compare against anchor-based likelihood-ratio tests and LASSO ([Psychometrika 88(4):1097-1122, 2023, DOI 10.1007/s11336-023-09930-9](https://doi.org/10.1007/s11336-023-09930-9); [arXiv 2110.11112](https://arxiv.org/abs/2110.11112v2)).
- Iterative purification (for example the iterative Wald approach) identifies non-DIF items as anchors to link groups. It controlled Type I error better than a one-shot Wald test ([PMC5965523](https://pmc.ncbi.nlm.nih.gov/articles/PMC5965523)).
- LLM applications so far use DIF on benchmarks with model families as groups ([NeurIPS 2026 poster](https://neurips.cc/virtual/2026/poster/139203)), on LLM raters through Rasch "differential rater functioning", which found question-order bias in several models ([arXiv 2608.27463](https://arxiv.org/abs/2608.27463)), and in an audit framework built on differential test functioning ([Baldwin, Frontiers in Education 2025, DOI 10.3389/feduc.2025.1592037](https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1592037)).

### Inferences
- Mapping A, within the target. Persons are sampled replies, the group is the supported candidate, items are axes (per instruction), and the matching variable is the reply's total score across axes. DIF on axis a means the candidate shifts axis a beyond what the reply's overall level predicts. A uniform shift across all axes is impact and does not count as DIF.
- The reference group. With no control, the natural reference is one-vs-rest pooling (as in our registered test) or a multi-group procedure. Bechger and Maris show that the choice changes absolute DIF only through an arbitrary normalization. Pairwise relative DIF (axis a vs axis b, candidate c vs rest) is normalization-free and is the only quantity identified without an anchor.
- Mapping B, target vs population. Groups are models and items are candidate x instruction x axis cells. This is the consensus test of section 2 in DIF form.
- The identification lesson for our paper. The untuned base plays the role of a known anchor. Anchor-free DIF identifies absolute effects only if most items carry no DIF. Generic name effects that "move behavior in every model" are dense DIF and break this assumption. This gives a formal citation for why naive group-vs-group tests reject on untuned models, and for why a base (or another anchor) is needed for absolute claims.
- Fit: binary verdicts per reply are item responses, so stored verdict tables support DIF directly with no new sampling. With 16 samples per cell, MH strata on total score are sparse. Logistic-regression DIF with total score as a covariate suits the data better.
- The LLM judge is a rater. Differential rater functioning applies if the judge scores replies differently depending on which candidate the reply mentions, and the judge's effect is shared across target and proxy only if it depends on the reply alone.

### Gaps
- I found no DIF analysis of LLM identity or political bias that uses candidates as the groups.
- I did not retrieve multi-group MH procedures or anchor-selection comparisons (for example Kopf, Zeileis and Strobl 2015) this session.

## 4. Self-consistency on the target alone: replicability, sign consistency, and directional tests

### Takeaway
Replication across independent instruction sets, paraphrases, contexts, or axis families shows that a group effect is stable. Stability is also a property of generic name effects learned in pretraining, so replicability alone cannot separate a covert objective from a generic association. A directional test helps only when the direction is fixed in advance and independent of the names. The strongest design randomizes which candidate the objective favors across model organisms, because generic name effects cannot track a random assignment.

### Cited Findings
- Generic effects replicate strongly. 16 of 18 models chose Biden in all 100 runs ([arXiv 2410.24190](https://arxiv.org/abs/2410.24190)). The female-name preference held in all 22 models and disappeared under counterbalanced neutral labels ([arXiv 2505.17049](https://arxiv.org/abs/2505.17049)).
- One line of work traces cognitive biases mainly to pretraining, with instruction tuning playing a smaller role, so the base profile persists through tuning ([review of Itzhak et al. 2025](https://liner.com/review/planted-in-pretraining-swayed-by-finetuning-case-study-on-origins)).
- ICE-Guard's "intervention consistency" measures the flip rate under a single-attribute swap with everything else fixed. Its abstract gives no null or decision rule ([arXiv 2603.18530](https://arxiv.org/abs/2603.18530)).
- In membership inference, comparing the target against its own perturbed neighbours replaced a reference model and beat reference-based attacks under realistic assumptions ([arXiv 2305.18462](https://arxiv.org/abs/2305.18462)). This is a working example of self-reference replacing an external reference, in a task where the nuisance (sample difficulty) is local to each input.
- Political-opinion answers from LLMs shift when the forced-choice format or paraphrase changes ([Röttger et al., arXiv 2402.16786](https://arxiv.org/abs/2402.16786); not retrieved this session). Prompt format alone can move accuracy substantially ([Sclar et al., arXiv 2310.11324](https://arxiv.org/abs/2310.11324); not retrieved this session).
- Partial-conjunction tests ask whether an effect holds in at least u of n studies, which gives a formal replicability claim ([Benjamini and Heller, Biometrics 64(4), 2008, DOI 10.1111/j.1541-0420.2008.01049.x](https://doi.org/10.1111/j.1541-0420.2008.01049.x); not retrieved this session).

### Inferences
- Sign consistency. With m candidates and k independent condition sets, under a null that the favored candidate is random in each set, the chance of the same favorite in all k sets is m^-(k-1). A rejection shows a stable model-name pairing. Pretraining associations are stable too, so it does not show tuning.
- Partial conjunction across condition families (instruction sets, paraphrase sets, axis families) states "the effect replicates in at least u of n families". It sharpens the claim of stability but leaves the generic-vs-trained question untouched.
- Directional tests. With two candidates the signed test equals the unsigned test, so direction adds nothing. With m > 2 candidates and a pre-specified favored candidate X, a one-sided X-vs-rest test is informative. Under a generic-effects null, a generic effect points at an unrelated X with probability about 1/m, so one model yields weak evidence.
- Randomized objective assignment. If model organisms are trained with the favored candidate drawn at random, generic name effects are independent of the assignment. A permutation test over assignments ("does the favored candidate match the assigned one more often than chance") is then valid without any base model. It applies to organisms we train and does not apply to served models.
- Axis-family contrast. If the documented objective predicts which axes move (for example persuasion axes rather than warmth or sycophancy axes), comparing those families within the target is a base-free contrast. It is valid only if generic name effects do not load on the same axes, and that assumption is untested.
- Fit: split-half replication across instructions and axis families runs on stored verdict tables. Randomized assignment needs organisms with different assigned candidates. It fits stored data only if such organisms already exist.

### Gaps
- I found no LLM paper that uses sign consistency or partial conjunction across conditions as evidence of trained, as opposed to generic, differential treatment.

## 5. Causal approaches on the target alone: token interventions, mediation, and invariance

### Takeaway
Swapping the name in the prompt is already a causal intervention. It identifies the total effect of the group token on the target, but it cannot say whether that effect was trained. White-box mediation can split the total effect into paths, for example through an internal user-model representation versus through topic content. That locates where differential treatment flows. Untuned models also carry user models, so mediation does not supply the missing reference either.

### Cited Findings
- Feder et al. survey causal inference in NLP, covering both estimating causal effects of text and using causal formalisms for robustness and fairness ([Feder et al., TACL 2022, arXiv 2109.00725](https://arxiv.org/abs/2109.00725); not retrieved this session).
- Vig et al. apply causal mediation analysis to gender bias in pretrained Transformers, with neurons and attention heads as mediators, on three datasets. They find the bias effects sparse, synergistic, and decomposable into direct and indirect paths ([Vig et al., arXiv 2004.12265](https://arxiv.org/abs/2004.12265)).
- TalkTuner finds linear-probe representations of user age, gender, education and socioeconomic status inside LLaMa2Chat-13B. "Control probes" shift those representations, and users used the dashboard to expose biased behavior ([Chen et al., arXiv 2406.07882](https://arxiv.org/abs/2406.07882)).
- First-person fairness uses counterfactual variation of user demographics over millions of interactions, scored by an LLM research assistant and checked against human annotations ([arXiv 2410.19803](https://arxiv.org/abs/2410.19803)).
- Counterfactual token fairness (Garg et al., [arXiv 1809.10610](https://arxiv.org/abs/1809.10610)) and counterfactual invariance (Veitch et al., [arXiv 2106.00545](https://arxiv.org/abs/2106.00545)) define invariance of a predictor to a protected token as the target property (both not retrieved this session).

### Inferences
- Available interventions. (a) Swap the name in the user turn: the total effect, which we already have. (b) Swap the name inside a prefilled reply while holding the user's stated support fixed, or the reverse. This separates "whom the user supports" from "which candidate the text discusses". (c) Patch or steer a user-stance representation between conditions. (d) Set the user-model representation to neutral and measure the residual group effect.
- Nulls. For (c), the null is a zero indirect effect through the user-model mediator. A rejection shows the group effect flows through the model's representation of the user.
- What these can claim without a base: the total causal effect, a path decomposition, and where the effect lives. None of them separates trained from generic effects, since untuned and served models also model users (the TalkTuner probes; the Transluce finding that motivates our replication).
- An invariance test (H0: output invariant to the name) rejects in every model, as the paper itself observes. It is not a detector on its own.
- Fit: (a) runs on stored data. (b) needs new sampling with reply prefill (open weights, or an API that allows assistant prefill). (c) and (d) need white-box access, so they cannot run on served models.

### Gaps
- I found no paper that applies causal mediation to user-stance-dependent behavior to separate trained from generic effects.
- Transluce's user-modeling work is outside this note's scope and was not retrieved.

## 6. Distribution-shift and two-sample tests on embeddings with a model population as reference

### Takeaway
MMD and classifier two-sample tests on outputs are proven for "is this the same model" (Gao et al.). Our stored embeddings support within-target between-candidate tests now. Against a model population, raw cross-model tests always reject because models differ in style, so the comparison must be a difference in differences: the target's between-candidate shift against the population's between-candidate shifts.

### Cited Findings
- Model equality testing uses MMD with a simple string kernel. It reached median power 77.4% against a range of distortions with about 10 samples per prompt, and it released a dataset of 1 million completions ([arXiv 2410.20247](https://arxiv.org/abs/2410.20247); [ICLR 2025 proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d73234a13815fc1f9779dd17d89be9b4-Abstract-Conference.html)).
- Bias Similarity Measurement combines scalar, distributional, behavioral and representational signals into one cross-model similarity space ([arXiv 2410.12010](https://arxiv.org/abs/2410.12010v4)).
- The kernel two-sample test (Gretton et al., [JMLR 13:723-773, 2012](https://jmlr.org/papers/v13/gretton12a.html)) and classifier two-sample tests (Lopez-Paz and Oquab, [arXiv 1610.06545](https://arxiv.org/abs/1610.06545)) are the standard tools. Both are not retrieved this session.

### Inferences
- Within target. Compute MMD between reply embeddings for candidate c and the rest, per instruction, with a permutation null of exchangeable candidate labels. It runs on stored embeddings and rejects for generic effects too.
- Difference in differences against a population. Compute S_m = MMD_m(c vs rest) or the mean-embedding shift vector for each model m, and compare the target's value with the population's. The null is that the target's shift is a draw from the population's shift distribution. Every model's replies must use the same embedder, and the section 2 limits (K >= 19 for a rank test, shared biases absorbed) apply.
- Sample size. 16 samples per cell exceeds the roughly 10 per prompt in Gao et al., but model substitution is a larger change than a covert group effect. Their power does not transfer.
- Kernel choice. A Hamming string kernel worked best for model identity. Semantic group effects fit an embedding kernel better, which matches what we store.

### Gaps
- I found no paper that tests embedding-space group shifts of one LLM against a population of LLMs.
- I did not retrieve "Idiosyncrasies in LLMs" (arXiv 2502.12150), which reports that model outputs are highly distinguishable. Confirm it before citing it as the reason raw cross-model tests reject.

## 7. For each method: what it compares, its null, what it needs, what a rejection can claim, and fit to our data

### Takeaway
Without a base, only a randomized assignment of the favored candidate lets a test attribute an effect to a trained objective rather than to generic name effects. Every other substitute claims "differs from a reference" or "is stable". For served models with no base, population outlier tests are the only option, and a rejection claims atypicality. The cheapest step that bears on the paper's current claim is a proxy-swap null control on the untuned bases we already store.

### Cited Findings
- The sources for each row are cited in sections 1 to 6 above.

### Inferences

| Method | Compares | Null | Needs | A rejection shows | It cannot show | Fit to stored data |
|---|---|---|---|---|---|---|
| Registered base subtraction | Target gap minus its own base's gap, per cell | Equal gaps | Base weights; sampling and judging of base | Tuning changed the group effect | Which training step caused it | Yes |
| Proxy subtraction, other vendor | Target gap minus another model's gap | Equal gaps | Proxy sampled on same prompts and judge | Target differs from proxy | Tuning, since name effects and post-training differ by model | Yes for proxy-swap null controls among stored bases, if prompts and judge match |
| Proxy subtraction, same family | Target minus sibling base (other size) | Equal gaps | Sibling base sampled the same way | Target differs from sibling | Tuning, since scale shifts sycophancy | Only if a sibling is stored |
| Scaled or robust proxy regression | Residuals of target gaps on proxy gaps across cells | Residual = 0 in each cell | Proxy data; sparse d | Cell-specific departure from the shared pattern | Dense trained effects, which the slope absorbs | Yes, with proxy data |
| Population rank or meta-analytic outlier | Target statistic vs K models' statistics | Exchangeable with population | K >= 19 models for one rank test; parametric model per cell | Target is atypical | Tuning; biases shared across the population | No: needs new sampling |
| Logistic-regression or MH DIF within target | Axis-specific candidate effect given total score | No item-specific candidate effect | Verdict tables only | Effect is axis-specific beyond uniform impact | Absolute effects without an anchor; tuning | Yes |
| Anchor-free DIF (robust scaling, L1) | Same, with anchors estimated | Most items DIF-free | Sparsity of effects | Sparse outlier axes | Anything when generic effects are dense | Yes, but its assumption is likely violated |
| DIF, target vs population | Item functioning across models | No model-specific item effect | Population sampling | Target-specific cells | Tuning | No |
| Sign consistency and partial conjunction | Favored candidate across independent condition sets | Random favorite per set | Split of stored conditions | Stable favoritism | Tuning, since generic effects are stable | Yes |
| Directional test, randomized assignment | Favored candidate vs randomly assigned target candidate across organisms | Favored candidate independent of assignment | Several organisms with randomized targets | The trained objective drives the effect | Effects in served models | Only if such organisms exist |
| Input name swap (invariance) | Outputs across name swaps | Invariance | Stored samples | Group token has a causal effect | Tuning (rejects in every model) | Yes |
| Reply-prefix swap or mediation | Paths through user model vs content | Zero indirect effect | Prefill or white-box access | Path the effect takes | Tuning | No: new sampling and white-box |
| Embedding MMD within target | Candidate vs rest reply distributions | Exchangeable labels | Stored embeddings | Distribution shift by group | Tuning | Yes |
| Embedding difference in differences vs population | Target shift vs population shifts | Target shift drawn from population | Population replies with same embedder | Atypical shift | Tuning; shared shifts | No |

- Combining a within-target DIF or sign-consistency test with the registered base test does not add identification. It narrows which axes and conditions carry the base-adjusted effect.
- For the served-model replication, the defensible claims are within-target invariance rejections (the group token matters) and, given a population, atypicality. Neither claims a trained objective.

### Gaps
- Several fit judgments assume that the stored bases share prompts, candidates, instructions and judge with the targets, and that model organisms with different assigned candidates may exist. I did not check the code repo to confirm either point.
