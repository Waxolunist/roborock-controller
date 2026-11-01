PLATFORM ?= linux/arm64
TAG := $(shell git rev-parse --short HEAD)$(shell [ -z "$$(git status --porcelain --untracked-files=no)" ] || echo -dirty)
IMAGE := roborock_controller:$(TAG)

.PHONY: lint test image image-name

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

test:
	.venv/bin/pytest -q

image: lint test
	docker build --platform $(PLATFORM) -f docker/Dockerfile -t $(IMAGE) .
	@echo $(IMAGE)

image-name:
	@echo $(IMAGE)
