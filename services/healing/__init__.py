"""Governed self-healing: detect, diagnose, propose, shadow-test, approve, apply, verify.

Custos can only repair what it controls — how it gates a model's decisions. It
cannot retrain someone else's model, so a retrain is a recorded request to the
model's owner, never something Custos pretends to have done. And nothing here
changes a verdict until a named person has approved it. See docs/adr/0006.
"""
