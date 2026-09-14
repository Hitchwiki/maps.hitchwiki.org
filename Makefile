.PHONY: test test-python test-javascript test-javascript-coverage lint

# The default suite is deterministic: tests marked "network" exercise live
# Nostr relays and are intended for explicit monitoring, not local or PR runs.
test: test-python test-javascript

test-python:
	python -m pytest tests/ -v -m "not network" --cov=hitch --cov-report=term-missing --cov-report=xml

test-javascript:
	npm test

test-javascript-coverage:
	mkdir -p coverage/javascript
	node --experimental-test-coverage --test tests/*.test.js > coverage/javascript/summary.txt
	cat coverage/javascript/summary.txt

lint:
	ruff check .
