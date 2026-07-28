# System model

[Українська](../uk/SYSTEM_MODEL.md) · [Русский](../ru/SYSTEM_MODEL.md) · [Home](../../README.md)

This document is a starting hypothesis, not a finished standard. It exists so
scientists, engineers and domain experts can challenge it.

## Core entities

| Entity | Purpose |
| --- | --- |
| Material | Element, molecule, substance, mixture, commodity or product |
| Stock | Quantity of material in a bounded place and state at a point or interval in time |
| Flow | Transfer of material between stocks |
| Transformation | Process converting inputs into outputs, emissions, waste and heat |
| Location | Point, area, volume, facility, vehicle or administrative territory |
| Actor | Person, organization, state or other controlling entity |
| Observation | Source-backed claim about any entity or event |
| Energy transfer | Energy input, output, storage, useful work or dissipation |

## Minimum dimensions of a record

- material identity and composition;
- quantity, unit and measurement basis;
- time or time interval;
- geographic location and spatial resolution;
- physical state, concentration, grade and recoverability;
- legal owner, operator and relevant forms of control;
- source, method, timestamp and chain of provenance;
- uncertainty, confidence and competing estimates;
- transformation or flow connections;
- energy consumed, released, stored and dissipated.

## Accounting invariants

Within a declared boundary and period, inputs, outputs and stock changes should
reconcile within an explicit uncertainty range. A mismatch is not silently
removed: it is recorded as an unexplained residual that may reveal missing data,
measurement error, leakage or an incomplete model.

Every transformation must conserve relevant chemical elements. Every energy
record must define its accounting boundary and avoid counting the same energy
twice.

## Observations are not facts without provenance

Aftertime should retain source records rather than replacing them with a single
unqualified number. Estimates may conflict. The system should show who made each
claim, when, by which method, under which assumptions and with what uncertainty.

Political control is also time-dependent and may be disputed. The data model
should support parallel claims and evidence instead of declaring contested
assertions as timeless truth.

## Candidate first pilot

A useful pilot should be narrow enough to audit but rich enough to test the
model. Candidate criteria:

- one material with clear strategic or environmental importance;
- one bounded geography and time period;
- observable opening and closing stocks;
- several transport and transformation stages;
- at least two independent data sources;
- a measurable energy relationship;
- public data that can legally be redistributed or referenced.

The first pilot will be selected through an open design proposal.
