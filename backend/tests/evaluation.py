"""Standalone evaluation harness for the multi-agent pipeline.

Runs a labeled test set of 20 utterances through process_voice_input()
and reports intent / task-count / category / priority / deadline
accuracy plus dedup precision. Not a pytest module — run via
`python -m tests.evaluation` or `make evaluate`.
"""
