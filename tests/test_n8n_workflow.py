"""Structural validation of the n8n workflow JSON.

n8n is not installed here, so instead of importing the workflow we verify
everything an import needs: valid JSON, required node fields, known node
types, and that every connection references a node that actually exists.
Also asserts no secrets are hard-coded in the workflow file.
"""

import json
import re
import unittest
from pathlib import Path

WORKFLOW_FILE = (Path(__file__).resolve().parent.parent
                 / "n8n" / "customer-support-workflow.json")

KNOWN_NODE_TYPES = {
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.code",
    "n8n-nodes-base.if",
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.stickyNote",
}


class TestN8nWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
        cls.nodes = {n["name"]: n for n in cls.workflow["nodes"]}

    def test_valid_structure(self):
        self.assertIn("nodes", self.workflow)
        self.assertIn("connections", self.workflow)
        self.assertGreaterEqual(len(self.workflow["nodes"]), 8)

    def test_nodes_have_required_fields(self):
        for node in self.workflow["nodes"]:
            for field in ("id", "name", "type", "typeVersion", "position",
                          "parameters"):
                self.assertIn(field, node, f"node {node.get('name')}")

    def test_only_known_node_types(self):
        for node in self.workflow["nodes"]:
            self.assertIn(node["type"], KNOWN_NODE_TYPES,
                          f"unexpected node type {node['type']}")

    def test_single_webhook_trigger(self):
        webhooks = [n for n in self.workflow["nodes"]
                    if n["type"] == "n8n-nodes-base.webhook"]
        self.assertEqual(len(webhooks), 1)
        self.assertEqual(webhooks[0]["parameters"]["httpMethod"], "POST")
        self.assertTrue(webhooks[0]["parameters"]["path"])

    def test_connections_reference_existing_nodes(self):
        for source, outputs in self.workflow["connections"].items():
            self.assertIn(source, self.nodes, f"unknown source {source}")
            for branch in outputs["main"]:
                for conn in branch:
                    self.assertIn(conn["node"], self.nodes,
                                  f"unknown target {conn['node']}")

    def test_expected_flow_nodes_present(self):
        for name in ("Customer Message Webhook", "Validate Input",
                     "Classify Intent", "Get Answer", "Create Human Ticket",
                     "Respond to Customer", "Notify Human Support"):
            self.assertIn(name, self.nodes)

    def test_http_nodes_point_at_backend_env(self):
        for name in ("Classify Intent", "Get Answer"):
            url = self.nodes[name]["parameters"]["url"]
            self.assertIn("BACKEND_URL", url)
            self.assertNotIn("localhost:8000", url.replace(
                "($env.BACKEND_URL || 'http://localhost:8000')", ""))

    def test_no_hardcoded_secrets(self):
        text = WORKFLOW_FILE.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{8,}", text))
        self.assertNotIn("WEBHOOK_SECRET=", text)
        # The secret is only ever *referenced* via $env, never inlined.
        self.assertNotIn("s3cr3t", text)


if __name__ == "__main__":
    unittest.main()
