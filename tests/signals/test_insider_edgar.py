"""SEC Form 4 XML parsing (real-shape, no network)."""
from __future__ import annotations

from alpha_agent.signals.insider_edgar import _parse_form4_net

# Mirrors the real SEC Form 4 ownershipDocument structure (nonDerivativeTable
# with transactionCoding/transactionCode + transactionAmounts). Includes a
# buy (P/A), a sale (S/D), and a grant (A code) that must be ignored.
_FORM4 = b"""<?xml version="1.0"?>
<ownershipDocument>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>400</value></transactionShares>
        <transactionPricePerShare><value>50.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>9999</value></transactionShares>
        <transactionPricePerShare><value>50.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

# Same shape with an explicit default namespace (some filings carry one) — the
# parser must be namespace-agnostic.
_FORM4_NS = b"""<?xml version="1.0"?>
<ownershipDocument xmlns="http://www.sec.gov/edgar/ownership">
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>200</value></transactionShares>
        <transactionPricePerShare><value>10.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parses_signed_open_market_net_ignores_grants():
    # +1000*50 (buy) -400*50 (sale) = +30000; the A-code grant is excluded.
    assert _parse_form4_net(_FORM4) == 1000 * 50.0 - 400 * 50.0


def test_namespace_agnostic():
    assert _parse_form4_net(_FORM4_NS) == 200 * 10.0


def test_malformed_xml_is_zero_not_crash():
    assert _parse_form4_net(b"<not-xml") == 0.0
