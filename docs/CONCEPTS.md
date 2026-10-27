# Slide concept -> where it lives in the code

| Slide concept | File / function | One-line explanation |
|---|---|---|
| **Independent verifier** | `codecoach/verifier.py` `verify` | accepts a diagnosis only if a repair of the predicted class makes the hidden tests pass; never sees confidence or the true label |
| Executable tests as ground truth | `codecoach/problems.py`, `sandbox.py` `run_tests` | correctness = tests pass in a child process with a timeout |
| **Protected holdout** | `generator.py` `split_problems`, `build_splits`; `safety.py` `protected_hashes` | splits by problem; `test` and `handwritten` never used for selection; fixed files hashed |
| **Accept / reject gate** | `self_training.py` `gate` | reject unless dev macro-F1 improves by `min_delta` and no class drops more than `max_class_drop` |
| **Rollback** | `self_training.py` `self_train` | the candidate is a separate copy; the old teacher is replaced only on acceptance (failure leaves it untouched) |
| Pipeline can only tighten the gate | `self_training.py` `effective_min_delta` | `max(config, pipeline)`: a self-edit cannot loosen its own gate |
| **Archive (Darwin Godel Machine)** | `codecoach/archive.py` `Archive` | tree of every version with parent, edit, metrics, accepted flag, reason; rejected versions kept |
| Parent selection | `evolvable/improver.py` `choose_parent` | tournament of K accepted versions: pressure toward good parents, still some exploration |
| **Self-modifying source** | `code_editor.py` operators + `improver.propose_child` | AST edits of `evolvable/pipeline.py` (constrained program search) |
| **STOP utility (improver improves itself)** | `scripts/02_evolve.py` `Level2.utility` / `__call__` | old vs new improver propose B edits from the same parent with the same seeds; kept only if worth more on meta_dev |
| Why meta_dev | `generator.py` (split), `Level2.utility` | the improver is judged on data the pipeline was not selected on |
| **Reward-hacking guard** | `safety.py` (whitelist, static check, tamper hashes, isolated run); `config.py` (frozen, not editable); `code_editor.py` bounds | the system cannot edit its evaluator, gate, data or limits |
| **Model-collapse / diversity guard** | `evolvable/pipeline.py` `curate` (`PER_CLASS_CAP`, `balance`); retrain from scratch each round | cap per class, dedupe, never fine-tune on own outputs only |
| Verifier ablation | `codecoach/ablation.py` | verifier vs confidence-threshold pseudo-labels |
| Level 1 only vs Level 1 + 2 | `02_evolve.py --no-level2 --tag level1_only` | does editing the improver add anything? |
| **Soft targets** | `distillation.py` `distillation_loss` | the teacher's whole probability vector, not just its argmax |
| **Temperature T** | same, `softmax(logits / T)` | softens distributions so small probabilities become visible |
| **T squared** | same, `* T * T` | restores the KL gradient scale that shrinks like 1/T^2 |
| **alpha** | same | weight of hard-label CE vs distillation; `alpha = 1` means no distillation |
| **Hard-label baseline** | `03_distill.py` `student_hard` | same student, same data, `alpha = 1` |
| **Capacity gap** | `distillation.py` `build_student` (16 hidden) vs teacher (256-128) | the student is about 18x smaller; distillation is meant to close the quality gap |
| Size / latency | `evaluation.py` `model_size_kb`, `latency_ms` | KB of the saved state_dict; median of 200 single-sample forward passes, 1 thread |
| Failure handling | `evaluator.py`, `02_evolve.py` `run_level1` | `unsafe`, `crash`, `timeout`, `memory`, `duplicate`, `no_improvement`: each logged per generation |
| Real-time learning | `app/live_logic.py` `retrain_with_buffer`; `app/views/tryit.py`, `live.py` | verified snippets retrain a candidate that must pass the same gate |
