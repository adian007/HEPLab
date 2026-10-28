"""Shared coffea processors (ADR-0001, ADR-0006).

Processors consume schema-v1 chunks only — never native formats — which is
what lets the same processor run on real data and simulation.
"""
