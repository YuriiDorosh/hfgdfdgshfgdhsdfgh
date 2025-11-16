DC_DEV = docker compose -f docker-compose.dev.yml
DC_PROD = docker compose -f docker-compose.prod.yml

.PHONY: up-dev down-dev logs-dev build-dev ps-dev \
        up-prod down-prod logs-prod build-prod ps-prod

up-dev:
	$(DC_DEV) up -d

down-dev:
	$(DC_DEV) down

logs-dev:
	$(DC_DEV) logs -f

build-dev:
	$(DC_DEV) build

ps-dev:
	$(DC_DEV) ps

up-prod:
	$(DC_PROD) up -d

down-prod:
	$(DC_PROD) down

logs-prod:
	$(DC_PROD) logs -f

build-prod:
	$(DC_PROD) build

ps-prod:
	$(DC_PROD) ps
