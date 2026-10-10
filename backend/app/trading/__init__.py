"""Trading pipeline packages.

Mandatory flow (no bypass):

    Trade Proposal → Risk Engine → Order Validator → Broker Router → Broker Adapter

Import submodules directly to avoid circular imports.
"""

__all__: list[str] = []
