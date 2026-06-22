from __future__ import annotations

import unittest

from backend.app.infrastructure.mocks.adapters import capability_catalog


class MockAdapterTest(unittest.TestCase):
    def test_every_intelligence_capability_is_explicitly_not_implemented(self) -> None:
        capabilities = {item["name"]: item for item in capability_catalog()}
        self.assertEqual(capabilities["document_repository"]["state"], "available")
        for name, capability in capabilities.items():
            if name != "document_repository":
                self.assertEqual(capability["implementation"], "mock")
                self.assertEqual(capability["state"], "not_implemented")
