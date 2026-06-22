@echo off
call .venv\Scripts\activate
pip install torch==2.0.1 torchaudio==2.0.2
python -c "import df; print('DeepFilterNet imported successfully!')"
