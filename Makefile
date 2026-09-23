FLAGS ?=
PY := .venv/bin/python

.venv: requirements.txt
	python3 -m venv .venv && .venv/bin/pip install -qr requirements.txt && touch .venv

jaeger:
	docker compose up -d

run: .venv
	$(PY) agent.py $(FLAGS)

clean:
	rm -rf out/drafts

.PHONY: jaeger run clean
