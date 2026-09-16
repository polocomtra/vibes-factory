# ADR-001: Modular Monolith

- Status: Accepted
- Date: 2026-09-15

VibesFactory starts as a modular monolith with independently runnable background workers. Bounded domains remain explicit in code so services can be extracted later without paying the operational cost of microservices during the portfolio MVP.

