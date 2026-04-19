.PHONY: install run build clean dist-local publish-test publish gen-rss gen-rss-upload subtitle-gen help

PYTHON ?= python3
PIP ?= pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in editable mode with all dependencies
	$(PIP) install -e .

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info podcast/*.egg-info gen_podcast.egg-info

build: clean ## Build source and wheel distributions
	$(PIP) install --upgrade build
	$(PYTHON) -m build

gen-podcast: ## Run gen-podcast CLI run command(pass ARGS="..." for extra arguments)
	gen-podcast run $(ARGS)

gen-rss: ## Generate RSS feed XML from D1 podcast data
	gen-podcasts-xml gen_xml_from_d1_podcast

gen-rss-upload: ## Generate RSS feed XML and upload to Cloudflare R2
	gen-podcasts-xml gen_xml_from_d1_podcast --is-upload

subtitle-gen: ## Generate word-level subtitles for an AUDIO file via Gemini (AUDIO=path [LANG=zh] [ARGS="..."])
	@if [ -z "$(AUDIO)" ]; then echo "usage: make subtitle-gen AUDIO=path/to.mp3 [LANG=zh] [ARGS=\"--output-dir /tmp/subs\"]"; exit 2; fi
	subtitle-gen generate "$(AUDIO)" --language $(or $(LANG),en) $(ARGS)

dist-local: build ## Install the built wheel locally
	$(PIP) install dist/*.whl --force-reinstall

publish-test: build ## Publish package to TestPyPI (https://test.pypi.org/)
	$(PIP) install --upgrade twine
	$(PYTHON) -m twine upload --repository testpypi dist/*

publish: build ## Publish package to PyPI (https://pypi.org/)
	$(PIP) install --upgrade twine
	$(PYTHON) -m twine upload dist/*
