"""Starter files written by `metamorph init`."""

CONFIG = """\
# Metamorph configuration. Docs: https://github.com/DiorWachira/metamorph#configuration

target:
  # Call a Python function in-process...
  type: python
  callable: app:answer            # module:function, imported relative to this file
  # ...or an HTTP endpoint (the seed input is sent as the JSON body):
  # type: http
  # url: http://127.0.0.1:8000/answer
  # output_path: $.answer          # JSONPath to the answer in the response
  # headers: {Authorization: "Bearer ${APP_TOKEN}"}

seeds: seeds.jsonl

fields:
  text: question                  # the main natural-language field
  documents: documents            # retrieved context, for RAG relations (optional)

relations:
  - doc-order-invariance
  - distractor-invariance
  - typo-robustness
  - number-format-invariance
  - entity-swap-invariance
  # Promote a relation to BLOCKING once you trust it:
  # - id: doc-order-invariance
  #   mode: blocking

run:
  seed: 0                         # makes follow-ups reproducible
  samples: 1                      # source samples per input (self-variance baseline when > 1)
  concurrency: 8

gate:
  max_blocking_violations: 0
"""

SEEDS = """\
{"id": "mpesa", "tags": ["rag"], "input": {"question": "When did Wanjiru's favourite service M-Pesa launch?", "documents": ["M-Pesa was launched by Safaricom in March 2007.", "Nairobi is the capital of Kenya."]}}
{"id": "counties", "tags": ["rag"], "input": {"question": "How many counties does Kenya have?", "documents": ["The 2010 Constitution created 47 counties.", "Mount Kenya rises to 5199 metres."]}}
"""

APP = '''\
"""A placeholder target. Replace it with a call into your real application."""


def answer(payload: dict) -> str:
    return payload["documents"][0]
'''
