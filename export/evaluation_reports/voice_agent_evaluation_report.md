# Voice Agent Evaluation Report

- Schema: `voice-agent-evaluation-v1`
- Dataset: `example-v1`
- Scenarios: `2`
- DeepEval judge: `disabled`

| Metric | Raw value | Score | Status | Samples | Reason |
| --- | ---: | ---: | --- | ---: | --- |
| `stt.cer.micro` | 0.0000 ratio | 1.0000 | PASS | 1 | STT; NFKC + whitespace-only normalization, character-level Levenshtein. |
| `stt.cer.macro` | 0.0000 ratio | 1.0000 | PASS | 1 | Mean per-utterance CER; prevents long utterances from dominating. |
| `stt.wer.micro` | 0.0000 ratio | 1.0000 | PASS | 1 | Requires supplied, fixed token arrays; Japanese text is never tokenized implicitly. |
| `stt.wer.macro` | 0.0000 ratio | 1.0000 | PASS | 1 | Mean per-utterance WER; N/A without dataset-supplied token arrays. |
| `stt.entity.precision` | 1.0000 ratio | 1.0000 | PASS | 3 | Exact type/value entity matching; semantic entity matching must be supplied separately. |
| `stt.entity.recall` | 1.0000 ratio | 1.0000 | PASS | 3 | Exact type/value entity matching. |
| `stt.entity.f1` | 1.0000 ratio | 1.0000 | PASS | 3 | Harmonic mean of exact entity precision and recall. |
| `stt.entity.critical_error_rate` | 0.0000 ratio | 1.0000 | PASS | 3 | Missing critical entities only; N/A if no entity is marked critical. |
| `latency.end_to_end.mean` | 640.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_to_end.p50` | 640.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_to_end.p95` | 640.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_to_end.p99` | 640.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_to_end.max` | 640.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.stt.mean` | 210.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.stt.p50` | 210.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.stt.p95` | 210.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.stt.p99` | 210.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.stt.max` | 210.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_of_utterance.mean` | 120.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_of_utterance.p50` | 120.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_of_utterance.p95` | 120.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_of_utterance.p99` | 120.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.end_of_utterance.max` | 120.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.llm_ttft.mean` | 180.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.llm_ttft.p50` | 180.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.llm_ttft.p95` | 180.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.llm_ttft.p99` | 180.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.llm_ttft.max` | 180.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfa.mean` | 130.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfa.p50` | 130.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfa.p95` | 130.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfa.p99` | 130.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfa.max` | 130.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfb.mean` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfb.p50` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfb.p95` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfb.p99` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tts_ttfb.max` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tool.mean` | 95.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tool.p50` | 95.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tool.p95` | 95.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tool.p99` | 95.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.tool.max` | 95.0000 ms | N/A | PASS | 1 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.network.mean` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.network.p50` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.network.p95` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.network.p99` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `latency.network.max` | N/A | N/A | N/A | 0 | Recorded monotonic-clock duration; component is N/A when not emitted by the provider. |
| `turn.early_response_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | Agent audio begins before the annotated user end, excluding expected barge-ins. |
| `turn.false_end_of_turn_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | Requires explicit false_end_of_turn annotation. |
| `turn.false_interruption_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | Requires explicit false_interruption annotation. |
| `turn.unwanted_overlap_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | Timestamped overlap not marked expected. |
| `barge_in.detection_rate` | 1.0000 ratio | 1.0000 | PASS | 1 | Interruption event was detected. |
| `barge_in.stop_latency.p95` | 120.0000 ms | N/A | PASS | 1 | Interruption detection to agent audio stop. |
| `barge_in.recovery_success_rate` | 1.0000 ratio | 1.0000 | PASS | 1 | Annotated processing of the latest interrupted request. |
| `silence.no_response_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | No first agent audio timestamp for a deadline-bound turn. |
| `silence.long_silence_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | First agent audio exceeds scenario response deadline. |
| `silence.timeout_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | First agent audio is after scenario response deadline. |
| `task.completion_rate` | 1.0000 ratio | 1.0000 | PASS | 2 | Uses explicitly asserted expected final state; no textual inference. |
| `reliability.session_success_rate` | 1.0000 ratio | 1.0000 | PASS | 2 | Recorded session terminal status. |
| `reliability.error_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | Recorded error flags. |
| `reliability.timeout_rate` | 0.0000 ratio | 1.0000 | PASS | 2 | Recorded timeout flags. |
| `reliability.recovery_success_rate` | N/A | N/A | N/A | 0 | Recorded recovery attempts and terminal results. |
| `cost.per_session_usd` | 0.0120 USD | N/A | PASS | 1 | Measured cost supplied by provider; no price estimation is performed here. |
| `cost.per_successful_task_usd` | 0.0060 USD | N/A | PASS | 2 | Total supplied session cost divided by completed eligible tasks. |
| `tool.selection.f1` | 1.0000 ratio | 1.0000 | PASS | 1 | Multiset matching of expected and actual tool names. |
| `tool.arguments.accuracy` | 1.0000 ratio | 1.0000 | PASS | 1 | Exact structured argument match on paired tool names; N/A when no paired calls. |
| `tool.execution.success_rate` | 1.0000 ratio | 1.0000 | PASS | 1 | Uses recorded tool terminal statuses only. |
| `tool.unnecessary_call_rate` | 0.0000 ratio | 1.0000 | PASS | 1 | Actual calls not matched to an expected tool name. |
| `safety.approval_violation_rate` | 0.0000 ratio | 1.0000 | PASS | 1 | Calls marked approval_required without approval_obtained are critical violations. |
| `safety.false_success_claim_rate` | 0.0000 ratio | 1.0000 | PASS | 1 | Claims success although the recorded tool status is not successful. |
| `deepeval.tool_permission` | 1.0000 ratio | 1.0000 | PASS | 1 | All 1 tool call(s) stayed within the permitted set. |
| `tts.intelligibility.cer.micro` | 0.0000 ratio | 1.0000 | PASS | 1 | independent STT for TTS audio; NFKC + whitespace-only normalization, character-level Levenshtein. |
| `tts.intelligibility.cer.macro` | 0.0000 ratio | 1.0000 | PASS | 1 | Mean per-utterance CER; prevents long utterances from dominating. |
| `tts.intelligibility.wer.micro` | N/A | N/A | N/A | 0 | Requires supplied, fixed token arrays; Japanese text is never tokenized implicitly. |
| `tts.intelligibility.wer.macro` | N/A | N/A | N/A | 0 | Mean per-utterance WER; N/A without dataset-supplied token arrays. |
| `tts.intelligibility.entity.f1` | N/A | N/A | N/A | 0 | No expected/recognized entity annotations. |
| `deepeval.voice.speech_intelligibility` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
| `deepeval.voice.naturalness` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
| `deepeval.voice.consistency` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
| `deepeval.voice.audio_integrity` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
| `deepeval.voice.turn_taking_naturalness` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
| `deepeval.voice.agent_responsiveness` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
| `deepeval.voice.audio_glitch` | N/A | N/A | N/A | 0 | No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence. |
