install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && pip install -r requirements.txt

install: install-backend install-frontend

run-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && streamlit run app.py --server.port 8501

test:
	cd backend && python -m pytest tests/ -v

evaluate:
	cd backend && python -m tests.evaluation

docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down
