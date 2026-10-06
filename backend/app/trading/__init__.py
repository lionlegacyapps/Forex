"""Trading pipeline package.

Automated order flow (planned — not implemented yet):

    Trade Proposal
      → Risk Engine
      → Order Validator
      → Broker Router
      → Broker Adapter

No strategy, AI model, external signal, or other component may bypass this
pipeline to place broker orders.
"""
