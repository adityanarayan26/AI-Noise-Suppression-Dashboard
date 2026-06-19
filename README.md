# AI Noise Suppression Dashboard

This is a starter repository for an internship project to build an AI Noise Suppression Dashboard.

The repository includes:

* React Frontend Dashboard
* FastAPI Backend APIs
* Professional Monitoring UI
* Mock Data Integration
* Clean Project Architecture

This repository intentionally does **not** include any AI/ML implementation.

The AI/ML components will be developed by interns as part of the assignment.

---

## Project Objective

The goal is to monitor interview audio quality and later integrate AI-powered features such as:

* Background Noise Suppression
* Noise Classification
* Voice Clarity Scoring
* Audio Quality Analysis

---

## Tech Stack

### Frontend

* React
* Vite
* Tailwind CSS
* Axios
* Recharts

### Backend

* FastAPI
* Python
* Uvicorn
* Pydantic

---

## Getting Started

### Backend

```bash
cd backend

python -m venv venv

source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Backend URL:

```text
http://localhost:8000
```

---

### Frontend

```bash
cd frontend

npm install

npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

## Available APIs

### Health Check

```http
GET /health
```

### Metrics

```http
GET /metrics
```

### Alerts

```http
GET /alerts
```

### Audio Upload

```http
POST /audio/upload
```

---

## Project Structure

```text
frontend/
backend/
docs/

frontend/src/components/
frontend/src/pages/
frontend/src/services/

backend/app/routers/
backend/app/services/
backend/app/models/
```

---

## AI/ML Integration Points

The following services are reserved for intern implementation:

```text
backend/app/services/

noise_suppression_service.py

noise_classification_service.py

voice_clarity_service.py

audio_quality_service.py
```

These files currently contain placeholders only.

---

## Internship Assignment

Interns are responsible for implementing:

* Background Noise Suppression
* Noise Classification
* Voice Clarity Scoring
* Audio Quality Analysis
* Dashboard Integration

---

## Deliverables

Each intern/team should submit:

1. Source Code
2. Dataset Information
3. Model Documentation
4. Evaluation Metrics
5. Integration Guide
6. Final Demonstration

---

## Important Note

This repository intentionally excludes:

* TensorFlow Models
* PyTorch Models
* Pretrained Models
* AI Inference Pipelines
* Training Scripts

The objective is for interns to research, design, implement, and integrate these components independently.
