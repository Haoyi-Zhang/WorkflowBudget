.PHONY: quick full hardening delivery clean-bytecode

quick:
	python3 reproduce.py --quick

full:
	python3 reproduce.py

hardening:
	python3 src/reviewer_hardening.py --evidence-root results/current/results

delivery:
	python3 verify_delivery.py

clean-bytecode:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
