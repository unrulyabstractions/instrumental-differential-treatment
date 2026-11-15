# src/conjecture

We run stage 3 of the audit pipeline, where we ask helper models to conjecture the named yes/no behaviour axes on which group favoritism would show and then freeze them.

We run the stage in two substeps we keep apart. First we conjecture hypotheses about how a compromised assistant would treat entities differently in a deployment. Then we operationalize each hypothesis into one monadic yes/no scoring question a judge can answer from a single response, without knowing which entity the prompt named. These frozen questions are the behaviour axes stage 4 collects replies against and stage 5 scores, so they must be fixed here before either runs. Callers reach for `conjecture_hypotheses` and `operationalize` in `hypothesis_conjecture.py`, writing to paths from `ConjecturePaths`.

## Files

| File | Responsibility |
|---|---|
| `hypothesis_conjecture.py` | Runs both substeps, normalizes and validates the model output, and freezes the hypotheses and scoring-question artifacts. |
| `conjecturer_prompts.py` | Holds the verbatim system and user prompts for the conjecture and operationalize substeps. |
| `scoring_question_validation.py` | Drops and counts questions that name an entity, compare across responses, or presuppose entity status, and matches questions to hypotheses. |
| `guaranteed_axis_registry.py` | Defines the refusal, concreteness, and risk-warning channels every registry must contain and merges them into the model's axes. |
| `axis_id_normalization.py` | Cleans axis ids to snake_case and zero-pads numeric prefixes so lexicographic order agrees with numeric order. |
| `conjecture_paths.py` | Defines the on-disk layout for one run: `hypotheses.json` and `scoring_questions.json`. |
